"""Pruebas de la página web que sirve la API."""

TEST_IDS = [
    "name",
    "subject",
    "grade",
    "classroom",
    "save",
    "students",
    "classroom-filter",
    "question",
    "send",
    "answer",
]


def test_home_page_has_every_control_and_never_uses_inner_html(
    sample_path, make_client
):
    response = make_client(sample_path).get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for test_id in TEST_IDS:
        assert f'data-testid="{test_id}"' in response.text
    assert "innerHTML" not in response.text
