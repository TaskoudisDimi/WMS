"""
Fill a business with demo data (see services/demo.py) for testing or recording a video.

    cd wms/backend
    venv/bin/python scripts/seed_demo.py --email you@example.com          # first business of that user
    venv/bin/python scripts/seed_demo.py --business-id <uuid>
    venv/bin/python scripts/seed_demo.py --email you@example.com --clean  # remove demo data

Uses SUPABASE_URL / SUPABASE_KEY from backend/.env (service role).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.supabase_client import supabase  # noqa: E402
from services import demo  # noqa: E402


def find_business(email: str | None, business_id: str | None) -> tuple[str, str]:
    if business_id:
        biz = supabase.table("businesses").select("id, owner_id").eq("id", business_id).maybe_single().execute()
        if not biz:
            sys.exit(f"Business {business_id} not found")
        return biz.data["id"], biz.data["owner_id"]
    users = supabase.auth.admin.list_users(per_page=1000)
    user = next((u for u in users if (u.email or "").lower() == email.lower()), None)
    if not user:
        sys.exit(f"No user with email {email}")
    m = supabase.table("business_members").select("business_id").eq("user_id", user.id).limit(1).execute()
    if not m.data:
        sys.exit(f"{email} has no business yet — sign in once so one is created")
    return m.data[0]["business_id"], user.id


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--email", help="seed the first business of this user")
    who.add_argument("--business-id", help="seed this business")
    ap.add_argument("--clean", action="store_true", help="remove previously seeded demo data and exit")
    args = ap.parse_args()

    biz_id, owner_id = find_business(args.email, args.business_id)
    demo.clean(biz_id)
    print("Removed previous demo data.")
    if not args.clean:
        print(demo.seed(biz_id, owner_id))
