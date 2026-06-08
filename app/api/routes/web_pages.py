from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["web"])

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title} — Iris</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{min-height:100vh;display:flex;align-items:center;justify-content:center;
         background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:24px}}
    .card{{background:#fff;border-radius:20px;box-shadow:0 4px 32px rgba(0,0,0,.10);
           width:100%;max-width:420px;overflow:hidden}}
    .hdr{{background:linear-gradient(135deg,#f97316,#ea580c);padding:28px;text-align:center}}
    .hdr span{{font-size:26px;font-weight:800;color:#fff;letter-spacing:-.5px}}
    .body{{padding:36px}}
    .icon{{font-size:48px;text-align:center;margin-bottom:16px}}
    h2{{font-size:20px;font-weight:700;color:#111;margin-bottom:8px}}
    p{{font-size:14px;color:#666;line-height:1.6;margin-bottom:16px}}
    .rule{{font-size:12px;color:#888;margin-bottom:16px;line-height:1.5}}
    input{{width:100%;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px;
           font-size:14px;color:#111;outline:none;margin-bottom:12px;transition:border .15s}}
    input:focus{{border-color:#f97316;box-shadow:0 0 0 3px rgba(249,115,22,.15)}}
    button{{width:100%;padding:13px;border:none;border-radius:10px;cursor:pointer;
            background:linear-gradient(135deg,#f97316,#ea580c);color:#fff;
            font-size:14px;font-weight:600;transition:opacity .15s}}
    button:hover{{opacity:.9}}
    button:disabled{{opacity:.6;cursor:not-allowed}}
    .err{{color:#dc2626;font-size:13px;margin-bottom:12px;display:none}}
    .hint{{font-size:12px;color:#aaa;text-align:center;margin-top:16px}}
  </style>
</head>
<body>
  <div class="card">
    <div class="hdr"><span>iris</span></div>
    <div class="body">{body}</div>
  </div>
  <script>{script}</script>
</body>
</html>"""


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page():
    body = """
      <div class="icon" id="icon">⏳</div>
      <h2 id="title">Verifying your email…</h2>
      <p id="msg">Please wait a moment.</p>
      <div id="extra"></div>
    """
    script = """
      (async () => {
        const qs     = window.location.search;
        const token  = new URLSearchParams(qs).get('token');
        const icon   = document.getElementById('icon');
        const title  = document.getElementById('title');
        const msg    = document.getElementById('msg');
        const extra  = document.getElementById('extra');

        if (!token) {
          icon.textContent  = '❌';
          title.textContent = 'Invalid link';
          msg.textContent   = 'No verification token found in this URL.';
          return;
        }
        try {
          const res = await fetch('/api/v1/auth/verify-email', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({token})
          });
          if (res.ok) {
            icon.textContent  = '✅';
            title.textContent = 'Email verified!';
            msg.textContent   = 'Your Iris account is now active. Open the Iris app on your computer to log in.';
          } else {
            const data = await res.json().catch(() => ({}));
            icon.textContent  = '❌';
            title.textContent = 'Link expired';
            msg.textContent   = data.detail || 'This verification link has expired or has already been used.';
            extra.innerHTML   = '<p class="hint">Open the Iris app and request a new verification email from the login screen.</p>';
          }
        } catch {
          icon.textContent  = '⚠️';
          title.textContent = 'Something went wrong';
          msg.textContent   = 'Could not reach the Iris server. Please try again later.';
        }
      })();
    """
    return HTMLResponse(
        _SHELL.format(title="Verify Email", body=body, script=script),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page():
    body = """
      <div id="form-view">
        <h2>Reset your password</h2>
        <p>Enter a new password for your Iris account.</p>
        <p class="rule">At least 8 characters, 1 number, and 1 special character (@$!%*?&amp;)</p>
        <div class="err" id="err"></div>
        <input type="password" id="pw1" placeholder="New password" autocomplete="new-password"/>
        <input type="password" id="pw2" placeholder="Confirm new password" autocomplete="new-password"/>
        <button id="btn" onclick="submitReset()">Update password</button>
      </div>
      <div id="success-view" style="display:none;text-align:center">
        <div class="icon">✅</div>
        <h2>Password updated!</h2>
        <p>Open the Iris app on your computer and log in with your new password.</p>
      </div>
    """
    script = """
      const token = new URLSearchParams(window.location.search).get('token');
      if (!token) {
        document.getElementById('err').style.display = 'block';
        document.getElementById('err').textContent = 'Invalid link — no token found.';
        document.getElementById('btn').disabled = true;
      }

      async function submitReset() {
        const btn  = document.getElementById('btn');
        const err  = document.getElementById('err');
        const pw1  = document.getElementById('pw1').value;
        const pw2  = document.getElementById('pw2').value;
        err.style.display = 'none';

        if (pw1 !== pw2) {
          err.textContent = 'Passwords do not match.';
          err.style.display = 'block';
          return;
        }
        if (!/^(?=.*[0-9])(?=.*[@$!%*?&]).{8,72}$/.test(pw1)) {
          err.textContent = 'Password must be at least 8 characters with 1 number and 1 special character.';
          err.style.display = 'block';
          return;
        }

        btn.disabled = true;
        btn.textContent = 'Updating…';
        try {
          const res = await fetch('/api/v1/auth/reset-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({token, new_password: pw1})
          });
          if (res.ok) {
            document.getElementById('form-view').style.display = 'none';
            document.getElementById('success-view').style.display = 'block';
          } else {
            const data = await res.json().catch(() => ({}));
            err.textContent = data.detail || 'This link has expired or is invalid. Please request a new password reset from the app.';
            err.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Update password';
          }
        } catch {
          err.textContent = 'Could not reach the Iris server. Please try again later.';
          err.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Update password';
        }
      }
    """
    return HTMLResponse(
        _SHELL.format(title="Reset Password", body=body, script=script),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
