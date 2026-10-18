from db.supabase_client import supabase


def resolve_supplier(business_id: str, name: str | None, cache: dict | None = None) -> str | None:
    """Return the supplier id for `name`, creating the supplier if needed."""
    if not name or not name.strip():
        return None
    name = name.strip()
    key = name.lower()
    if cache is not None and key in cache:
        return cache[key]
    rows = supabase.table("suppliers").select("id, name").eq("business_id", business_id).execute().data or []
    match = next((r["id"] for r in rows if r["name"].lower() == key), None)
    if not match:
        match = supabase.table("suppliers").insert({"business_id": business_id, "name": name}).execute().data[0]["id"]
    if cache is not None:
        cache[key] = match
    return match
