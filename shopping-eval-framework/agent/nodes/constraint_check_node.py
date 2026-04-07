from agent.tracing import traced_node

OPS = {
    "lte": lambda actual, val: actual <= val,
    "gte": lambda actual, val: actual >= val,
    "eq": lambda actual, val: actual == val,
    "contains": lambda actual, val: str(val).lower() in str(actual).lower(),
}


def check_constraint(product: dict, constraint: dict) -> tuple:
    """Returns (passes, violation_or_None)"""
    field = constraint["field"]
    op = constraint["op"]
    required_value = constraint["value"]

    # Navigate into specs if needed
    actual = product.get("specs", {}).get(field) or product.get(field)

    if actual is None:
        # Missing spec — cannot verify constraint is satisfied
        # Treat missing hard constraints as violations
        if constraint.get("is_hard"):
            return False, {
                "product_id": product["id"],
                "violated_constraint": field,
                "actual": None,
                "required": f"{op} {required_value}",
                "reason": "spec_missing"
            }
        return True, None  # soft constraint — missing is OK

    op_fn = OPS.get(op)
    if not op_fn:
        return True, None  # unknown op — skip

    passes = op_fn(actual, required_value)
    if not passes:
        return False, {
            "product_id": product["id"],
            "violated_constraint": field,
            "actual": actual,
            "required": f"{op} {required_value}",
            "reason": "constraint_violated"
        }
    return True, None


@traced_node("ConstraintCheckNode")
def constraint_check_node(state: dict) -> dict:
    products = state.get("candidate_products", [])
    constraints = [c for c in state.get("parsed_constraints", []) if c.get("is_hard")]

    filtered = []
    violations = []

    for product in products:
        product_passes = True
        for constraint in constraints:
            passes, violation = check_constraint(product, constraint)
            if not passes:
                violations.append(violation)
                product_passes = False
                break  # one violation is enough to exclude
        if product_passes:
            filtered.append(product)

    return {
        **state,
        "filtered_products": filtered,
        "constraint_violations": violations
    }
