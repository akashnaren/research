PREAMBLE = """You are completing one shopping task on MiniShop.

Rules:
- Follow the task exactly. Do not buy extra items.
- If the requested item or size cannot be purchased, stop.
- Do not invent catalog pages that you have not observed.
- The application backend is the source of truth.

This study uses one general model for every interface condition. Do not assume a computer-use specialist."""

C1_BLOCK = """Condition C1: you receive a screenshot of the human MiniShop page.

Return a single JSON object:
{"action": "click", "x": 120, "y": 240}
{"action": "type", "text": "18 Cedar Ave, Portland"}
{"action": "scroll", "dy": 400}
{"action": "done"}

Coordinates are CSS pixels from the top-left of the screenshot (same as the viewport).
Click a field before typing. Use done when the task is complete or cannot be completed."""

C2_BLOCK = """Condition C2: you receive an accessibility tree of the same human MiniShop page.

Return a single JSON object:
{"action": "click", "name": "Navy Crew Tee"}
{"action": "fill", "name": "Shipping address", "text": "18 Cedar Ave, Portland"}
{"action": "scroll", "dy": 400}
{"action": "done"}

`name` must match an accessible name in the tree (button, link, or textbox).
Use done when the task is complete or cannot be completed."""

C3_BLOCK = """Condition C3: you call flat tools. There is no current-view document.

Use list_products to learn product ids, then open_product, set_size, add_to_cart, go_catalog, go_checkout, set_address, and pay.
Tool results are short status objects or a product list. They are not a view document.

If the task is complete or cannot be completed, stop without another tool call."""

C4_BLOCK = """Condition C4: you receive a JSON view document with view, state, entities, and affordances.

Return a single JSON object:
{"name": "open_product", "arguments": {"product_id": "tee-navy"}}

Use only affordance ids. Prefer enabled affordances. Argument values must match the affordance input schema.
Out-of-stock sizes are omitted from enums. Disabled pay/add_to_cart means preconditions failed.
If the task is complete or cannot be completed, return {"name": "done", "arguments": {}}."""


def system_prompt(condition: str) -> str:
    blocks = {"C1": C1_BLOCK, "C2": C2_BLOCK, "C3": C3_BLOCK, "C4": C4_BLOCK}
    return PREAMBLE + "\n\n" + blocks[condition]
