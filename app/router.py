def route_category(category: str) -> str:
    routes = {
        "claims": "Claims Team",
        "warehouse_ops": "Warehouse Operations",
        "finance": "Finance Team",
        "inventory": "Inventory Control",
        "logistics": "Logistics Team",
        "general": "Customer Service Desk",
    }
    return routes.get(category, "Customer Service Desk")