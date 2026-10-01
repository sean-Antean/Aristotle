import { getServerClient } from "@/lib/supabase";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// The dashboard's "Refresh now" button posts here. We stamp a request row in
// Supabase; a local watcher on the trading machine sees it and runs
// reconcile.py --push, so the click triggers a genuine fresh Schwab pull.
export async function POST() {
  try {
    const supabase = getServerClient();
    const { error } = await supabase
      .from("control")
      .upsert({ id: 1, refresh_requested_at: new Date().toISOString() });
    if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message ?? "error" }, { status: 500 });
  }
}
