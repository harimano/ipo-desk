// The gated dashboard. Cloudflare Access (email one-time PIN, an allowlist of addresses) sits in front of this
// Worker; this file re-checks Access's signed JWT on EVERY request before serving a byte of _site/, so a
// misconfigured or removed Access application fails closed, never open. No code here ever sees a password:
// Access does the login, we only verify its signature.
//
// Vars (deploy.yml passes them from repo variables; never secrets, never in wrangler.toml):
//   TEAM_DOMAIN  "<team>.cloudflareaccess.com"  — Zero Trust → Settings → Custom Pages → Team domain
//   POLICY_AUD   the Access application's Audience (AUD) tag — Zero Trust → Access → Applications → the app
//
// Access puts the JWT in the Cf-Access-Jwt-Assertion header (and a CF_Authorization cookie). It is RS256-signed
// by keys published at https://<team>.cloudflareaccess.com/cdn-cgi/access/certs; those are cached an hour.

const CERTS_TTL_MS = 60 * 60 * 1000;
let certs = { at: 0, keys: {} };            // kid -> CryptoKey; module-level, so it survives across requests in one isolate

async function keyFor(kid, env) {
  if (!certs.keys[kid] || Date.now() - certs.at > CERTS_TTL_MS) {
    const r = await fetch(`https://${env.TEAM_DOMAIN}/cdn-cgi/access/certs`);
    if (!r.ok) throw new Error(`certs answered ${r.status}`);
    const body = await r.json();
    const keys = {};
    for (const k of body.keys || []) {
      keys[k.kid] = await crypto.subtle.importKey("jwk", k, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    }
    certs = { at: Date.now(), keys };
  }
  const key = certs.keys[kid];
  if (!key) throw new Error("unknown signing key");
  return key;
}

function b64url(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(s + "=".repeat((4 - (s.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const decodeJson = part => JSON.parse(new TextDecoder().decode(b64url(part)));

// Returns the verified claims (email among them) or throws.
async function verify(token, env) {
  if (!token) throw new Error("no token");
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) throw new Error("malformed token");
  const header = decodeJson(h);
  if (header.alg !== "RS256") throw new Error(`alg ${header.alg}`);
  const key = await keyFor(header.kid, env);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64url(s), new TextEncoder().encode(`${h}.${p}`));
  if (!ok) throw new Error("bad signature");
  const claims = decodeJson(p);
  const now = Math.floor(Date.now() / 1000);
  if (typeof claims.exp !== "number" || claims.exp < now) throw new Error("expired");
  if (typeof claims.nbf === "number" && claims.nbf > now + 60) throw new Error("not yet valid");
  if (claims.iss !== `https://${env.TEAM_DOMAIN}`) throw new Error("wrong issuer");
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(env.POLICY_AUD)) throw new Error("wrong audience");
  return claims;
}

function tokenFrom(request) {
  const h = request.headers.get("Cf-Access-Jwt-Assertion");
  if (h) return h;
  const m = /(?:^|;\s*)CF_Authorization=([^;]+)/.exec(request.headers.get("Cookie") || "");
  return m ? m[1] : "";
}

const text = (body, status, extra) =>
  new Response(body + "\n", { status, headers: Object.assign({ "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }, extra || {}) });

export default {
  async fetch(request, env) {
    if (!env.TEAM_DOMAIN || !env.POLICY_AUD) {
      return text("ipo-desk: the gate is not configured (TEAM_DOMAIN / POLICY_AUD), so nothing is served.", 503);
    }
    let claims;
    try {
      claims = await verify(tokenFrom(request), env);
    } catch (e) {
      // With Access in front a visitor never gets here unauthenticated; this answers only when Access is missing
      // or the token is stale. Say so plainly, never serve.
      return text(`ipo-desk: sign-in required (${e.message}). Open the page again to sign in.`, 401);
    }
    const url = new URL(request.url);
    if (url.pathname === "/logout") return Response.redirect(`https://${env.TEAM_DOMAIN}/cdn-cgi/access/logout`, 302);
    if (url.pathname === "/whoami") return text(claims.email || "(no email claim)", 200);

    const res = await env.ASSETS.fetch(request);
    const headers = new Headers(res.headers);
    headers.set("X-Robots-Tag", "noindex, nofollow");       // a gated page is not for search engines
    headers.set("Referrer-Policy", "no-referrer");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  },
};
