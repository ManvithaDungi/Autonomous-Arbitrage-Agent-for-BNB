import { NextResponse } from 'next/server';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:53421";

export async function GET() {
  try {
    const response = await fetch(`${API_BASE}/api/tokens`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { tokens: [], error: data?.error || "Token fetch failed" },
        { status: response.status }
      );
    }
    return NextResponse.json({ tokens: data.tokens || [] });
  } catch (error) {
    return NextResponse.json({ tokens: [], error: error.message }, { status: 500 });
  }
}
