from src.app.notion import parse_page_to_task


def test_parse_page_to_task_falls_back_to_first_title_property():
    page = {
        "id": "1234abcd",
        "properties": {
            "Custom name": {
                "type": "title",
                "title": [
                    {
                        "plain_text": "My Task",
                        "text": {"content": "My Task"},
                    }
                ],
            },
            "Title": {
                "type": "rich_text",
                "rich_text": [],
            },
        },
    }

    task = parse_page_to_task(page)

    assert task.title == "My Task"
    assert task.notion_id == "1234abcd"


def test_parse_page_to_task_falls_back_to_page_id():
    page = {
        "id": "abcd-efgh",
        "properties": {},
    }

    task = parse_page_to_task(page)

    assert task.title == "abcd-efgh"
