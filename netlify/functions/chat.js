// Netlify Function: Proxy chat requests to Dify API
// Environment variables: DIFY_API_URL, DIFY_API_KEY

export default async function handler(req, context) {
  // Only allow POST
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  const DIFY_API_URL = process.env.DIFY_API_URL;
  const DIFY_API_KEY = process.env.DIFY_API_KEY;

  if (!DIFY_API_URL || !DIFY_API_KEY) {
    return new Response(JSON.stringify({ error: "Server config missing" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const body = await req.text();

    const response = await fetch(DIFY_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DIFY_API_KEY}`,
      },
      body: body,
    });

    if (!response.ok) {
      const errText = await response.text();
      return new Response(errText, {
        status: response.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Stream the SSE response directly back to the client
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: "Proxy error: " + err.message }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}

export const config = {
  path: "/api/chat",
};
