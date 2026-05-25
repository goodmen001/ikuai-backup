LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iKuai Backup - 登录</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei','PingFang SC',sans-serif;min-height:100vh;display:flex;justify-content:center;align-items:center;background:linear-gradient(135deg,#1a1a2e,#16213e)}
.login-box{background:#fff;border-radius:12px;padding:40px;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.login-box h1{font-size:22px;text-align:center;margin-bottom:8px;color:#1a73e8}
.login-box .sub{text-align:center;color:#888;font-size:13px;margin-bottom:28px}
.login-box .error{color:#e74c3c;font-size:13px;text-align:center;margin-bottom:12px;display:none;padding:8px;background:#fff0f0;border-radius:6px}
.login-box .form-group{margin-bottom:16px}
.login-box .form-group label{display:block;font-size:13px;font-weight:600;color:#555;margin-bottom:4px}
.login-box .form-group input{width:100%;padding:10px 14px;border:2px solid #eee;border-radius:8px;font-size:14px;transition:.2s;outline:none}
.login-box .form-group input:focus{border-color:#1a73e8}
.login-box .btn{width:100%;padding:11px;background:#1a73e8;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;transition:.2s}
.login-box .btn:hover{background:#1557b0}
.login-box .btn:disabled{opacity:.6;cursor:not-allowed}
</style>
</head>
<body>
<div class="login-box">
  <h1>iKuai Backup</h1>
  <div class="sub">请输入管理员凭证</div>
  <div class="error" id="loginError">用户名或密码错误</div>
  <form id="loginForm" onsubmit="return false">
    <div class="form-group"><label>用户名</label><input id="loginUser" type="text" placeholder="admin" autocomplete="username"></div>
    <div class="form-group"><label>密码</label><input id="loginPass" type="password" placeholder="••••••" autocomplete="current-password"></div>
    <button class="btn" id="loginBtn" type="button" onclick="doLogin()">登 录</button>
  </form>
</div>
<script>
async function doLogin() {
  var btn = document.getElementById('loginBtn');
  var err = document.getElementById('loginError');
  btn.disabled = true; err.style.display = 'none';
  try {
    var r = await fetch('/api/login', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username: document.getElementById('loginUser').value, password: document.getElementById('loginPass').value})
    });
    var d = await r.json();
    if (d.success) { window.location.href = '/'; }
    else { err.style.display = 'block'; }
  } catch(e) { err.textContent = '网络错误'; err.style.display = 'block'; }
  btn.disabled = false;
}
document.getElementById('loginPass').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doLogin();
});
</script>
</body>
</html>"""
