import json
from urllib.parse import urlparse, parse_qs

from workers import WorkerEntrypoint, Response

# Lazy imports to avoid exceeding Worker startup CPU limits
# All heavy imports are deferred until first request/scheduled run


class Default(WorkerEntrypoint):
    @staticmethod
    def _has_valid_admin_token(request, query, bindings) -> bool:
        if not getattr(bindings, "admin_token", ""):
            return False
        token = (
            request.headers.get("X-Admin-Token")
            or request.headers.get("Authorization")
            or query.get("token", [None])[0]
        )
        return token == bindings.admin_token

    async def fetch(self, request):
        """
        Handle HTTP requests to the worker.
        Supports Notion webhook endpoint at /webhook/notion
        """
        # Lazy import to avoid startup CPU limit
        try:
            from app import ensure_http_patched  # type: ignore
            from app.webhook import handle as webhook_handle  # type: ignore
        except ImportError:
            try:
                from __init__ import ensure_http_patched  # type: ignore
            except ImportError:
                def ensure_http_patched():
                    pass
            from webhook import handle as webhook_handle  # type: ignore
        
        ensure_http_patched()
        
        url = str(request.url)
        method = request.method
        parsed = urlparse(url)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.endswith("/webhook/notion") and method == "POST":
            return await webhook_handle(request, self.env)
        
        if path.endswith("/admin/full-sync") and method == "POST":
            try:
                from app.config import get_bindings  # type: ignore
                from app.engine import run_full_sync  # type: ignore
            except ImportError:
                from config import get_bindings  # type: ignore
                from engine import run_full_sync  # type: ignore
            bindings = get_bindings(self.env)
            if not self._has_valid_admin_token(request, query, bindings):
                return Response("Unauthorized", status=401)
            result = await run_full_sync(bindings)
            return Response(json.dumps(result), headers={"Content-Type": "application/json"})

        if path.endswith("/admin/settings"):
            try:
                from app.config import get_bindings  # type: ignore
                from app.stores import load_settings, update_settings  # type: ignore
            except ImportError:
                from config import get_bindings  # type: ignore
                from stores import load_settings, update_settings  # type: ignore
            bindings = get_bindings(self.env)
            if not self._has_valid_admin_token(request, query, bindings):
                return Response("Unauthorized", status=401)
            if method == "GET":
                data = await load_settings(bindings.state)
                return Response(json.dumps(data), headers={"Content-Type": "application/json"})
            if method in {"POST", "PUT"}:
                try:
                    payload = await request.json()
                except Exception:
                    payload = {}
                updates = {}
                if "calendar_name" in payload:
                    updates["calendar_name"] = str(payload["calendar_name"]).strip() or None
                if "calendar_color" in payload:
                    updates["calendar_color"] = str(payload["calendar_color"]).strip() or None
                if "full_sync_interval_minutes" in payload:
                    try:
                        minutes = int(payload["full_sync_interval_minutes"])
                        if minutes <= 0:
                            raise ValueError
                        updates["full_sync_interval_minutes"] = minutes
                    except Exception:
                        return Response("Invalid full_sync_interval_minutes", status=400)
                data = await update_settings(bindings.state, **updates)
                return Response(json.dumps(data), headers={"Content-Type": "application/json"})
            return Response("Method Not Allowed", status=405)
        
        # Debug endpoint to check JS APIs and pyodide-http status
        if path.endswith("/admin/debug") and method == "GET":
            try:
                from app.config import get_bindings  # type: ignore
            except ImportError:
                from config import get_bindings  # type: ignore
            bindings = get_bindings(self.env)
            if not self._has_valid_admin_token(request, query, bindings):
                return Response("Unauthorized", status=401)
            debug_info = {}
            
            # Check for XMLHttpRequest
            try:
                from js import XMLHttpRequest
                debug_info["has_XMLHttpRequest"] = True
                debug_info["XMLHttpRequest_type"] = str(type(XMLHttpRequest))
            except ImportError as e:
                debug_info["has_XMLHttpRequest"] = False
                debug_info["XMLHttpRequest_error"] = str(e)
            
            # Check for fetch
            try:
                from js import fetch
                debug_info["has_fetch"] = True
                debug_info["fetch_type"] = str(type(fetch))
            except ImportError as e:
                debug_info["has_fetch"] = False
                debug_info["fetch_error"] = str(e)
            
            # Check pyodide-http status
            try:
                import pyodide_http
                debug_info["pyodide_http_version"] = pyodide_http.__version__
                debug_info["pyodide_http_should_patch"] = pyodide_http.should_patch()
            except Exception as e:
                debug_info["pyodide_http_error"] = str(e)
            
            return Response(json.dumps(debug_info, indent=2), headers={"Content-Type": "application/json"})

        return Response("", headers={"Content-Type": "text/plain"}, status=404)

    async def scheduled(self, controller, env, ctx):
        """
        Handle scheduled cron triggers (runs every 30 minutes).
        Performs a full Notion → Calendar rewrite.
        """
        # Lazy import to avoid startup CPU limit
        try:
            from app import ensure_http_patched  # type: ignore
            from app.config import get_bindings  # type: ignore
            from app.engine import run_full_sync, full_sync_due  # type: ignore
            from app.stores import load_settings  # type: ignore
        except ImportError:
            try:
                from __init__ import ensure_http_patched  # type: ignore
            except ImportError:
                def ensure_http_patched():
                    pass
            from config import get_bindings  # type: ignore
            from engine import run_full_sync, full_sync_due  # type: ignore
            from stores import load_settings  # type: ignore

        ensure_http_patched()
        bindings = get_bindings(self.env)
        settings = await load_settings(bindings.state)
        if not settings or full_sync_due(settings):
            await run_full_sync(bindings)
        else:
            print("[sync] scheduled run skipped (full sync interval not reached)")
