from migrator.concepts.keys import canonical_path, display_path, route_key, snake_case


def test_route_keys_ignore_param_names_and_slashes():
    assert route_key("get", "users", ":id") == "GET /users/{}"
    assert route_key("GET", "/users/", "{user_id}") == "GET /users/{}"
    assert route_key("post", "", "") == "POST /"
    assert canonical_path("/orders", ":id/cancel") == "/orders/{}/cancel"


def test_display_path_keeps_names():
    assert display_path("orders", ":id/cancel") == "/orders/{id}/cancel"
    assert display_path("/users", "{user_id}") == "/users/{user_id}"


def test_snake_case():
    assert snake_case("userId") == "user_id"
    assert snake_case("orders.createdAt") == "orders.created_at"
