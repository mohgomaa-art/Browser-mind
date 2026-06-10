# scripts/experiments/p8a_test_server.py
"""
P8A: Mock Web Server for Baseline Challenge.
Hosts a multi-environment controlled web app to support all 9 comparative tasks.
"""
import http.server
import socketserver
import urllib.parse
import json
import random
import sys

PORT = 8097

# Shared state
USERS = {"standard_user": "secret_sauce"}
CURRENT_OTPS = {"standard_user": "123456"}
VAULT_OTPS = {"standard_user": "123456"}
EMAILS = {"standard_user": []}
SESSIONS = set()
ORDERS = []

# Dynamic states for simulation
VAULT_FAIL = False  # If True, vault OTP is expired/invalid
EMAIL_DELAY = False  # If True, email takes longer to arrive
RESET_TIME = 0.0

class MockAppHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_html(self, content, status=200):
        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        username = query.get("username", ["standard_user"])[0]

        # Reset state helper
        # Reset state helper
        if path == "/reset-server-state":
            global USERS, CURRENT_OTPS, VAULT_OTPS, EMAILS, SESSIONS, ORDERS, VAULT_FAIL, EMAIL_DELAY, RESET_TIME
            import time
            RESET_TIME = time.time()
            USERS = {"standard_user": "secret_sauce"}
            otp = f"{random.randint(100000, 999999)}"
            CURRENT_OTPS = {"standard_user": otp}
            VAULT_OTPS = {"standard_user": otp}
            EMAILS = {"standard_user": []}
            SESSIONS = set()
            ORDERS = []
            VAULT_FAIL = "fail_vault" in query
            EMAIL_DELAY = "delay_email" in query
            
            if VAULT_FAIL:
                VAULT_OTPS["standard_user"] = "000000"  # Expired
                email_otp = f"{random.randint(100000, 999999)}"
                CURRENT_OTPS["standard_user"] = email_otp
                EMAILS["standard_user"].append({
                    "subject": "Your Security Code",
                    "body": f"Your verification code is {email_otp}."
                })
            else:
                VAULT_OTPS["standard_user"] = otp
                CURRENT_OTPS["standard_user"] = otp
                
            self.send_html("State Reset OK")
            return

        if path in ("/", "/login"):
            self.render_login(query.get("error", [""])[0])
        elif path == "/2fa":
            self.render_2fa(username, query.get("error", [""])[0])
        elif path == "/dashboard":
            self.render_dashboard(query.get("token", [""])[0])
        elif path == "/forgot-password":
            self.render_forgot_password(query.get("error", [""])[0])
        elif path == "/reset-password":
            token = query.get("token", [""])[0]
            self.render_reset_password(username, token)
        elif path == "/vault":
            self.render_vault(username)
        elif path == "/email-client":
            self.render_email_client(username)
        elif path == "/checkout":
            self.render_checkout()
        elif path == "/search":
            self.render_search(query.get("q", [""])[0])
        elif path == "/navigation":
            self.render_navigation(query.get("menu", [""])[0])
        elif path == "/filter":
            self.render_filter(query.get("size", [""])[0])
        elif path == "/profile":
            self.render_profile(query.get("msg", [""])[0])
        elif path == "/contact":
            self.render_contact(query.get("msg", [""])[0])
        else:
            self.send_html("404 Not Found", 404)

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length).decode("utf-8")
        params = urllib.parse.parse_qs(post_data)

        if path == "/login":
            username = params.get("username", [""])[0]
            password = params.get("password", [""])[0]
            if USERS.get(username) == password:
                self.send_response(303)
                self.send_header("Location", f"/2fa?username={username}")
                self.end_headers()
            else:
                self.send_response(303)
                self.send_header("Location", "/login?error=Invalid+credentials")
                self.end_headers()

        elif path == "/2fa":
            username = params.get("username", ["standard_user"])[0]
            otp = params.get("otp", [""])[0]
            if CURRENT_OTPS.get(username) == otp and otp != "000000":
                token = f"session_{random.randint(1000, 9999)}"
                SESSIONS.add(token)
                self.send_response(303)
                self.send_header("Location", f"/dashboard?token={token}")
                self.end_headers()
            else:
                self.send_response(303)
                self.send_header("Location", f"/2fa?username={username}&error=Invalid+security+code")
                self.end_headers()

        elif path == "/forgot-password":
            username = params.get("username", [""])[0]
            if username in USERS:
                token = f"reset_{random.randint(1000, 9999)}"
                reset_link = f"http://127.0.0.1:{PORT}/reset-password?username={username}&token={token}"
                EMAILS[username].append({
                    "subject": "Password Reset Link",
                    "body": f"Please reset your password by clicking this link: {reset_link}"
                })
                self.send_html(f"<html><body><p id='status'>Reset email sent.</p><a href='/login'>Back to Login</a></body></html>")
            else:
                self.send_response(303)
                self.send_header("Location", "/forgot-password?error=User+not+found")
                self.end_headers()

        elif path == "/reset-password":
            username = params.get("username", [""])[0]
            password = params.get("password", [""])[0]
            if username in USERS:
                USERS[username] = password
                self.send_html(f"<html><body><p id='status'>Password updated successfully!</p><a href='/login' id='login-link'>Go to Login</a></body></html>")
            else:
                self.send_html("Reset failed", 400)

        elif path == "/checkout":
            product = params.get("product", [""])[0]
            qty = params.get("quantity", ["1"])[0]
            address = params.get("address", [""])[0]
            card = params.get("card", [""])[0]

            order_id = f"ORDER-{random.randint(10000, 99999)}"
            ORDERS.append({"order_id": order_id, "product": product, "qty": qty})

            EMAILS["standard_user"].append({
                "subject": "Order Confirmation",
                "body": f"Thank you for your order! Order ID: {order_id}. Product: {product}. Quantity: {qty}."
            })
            
            self.send_html(f"""
            <html><body>
                <h2>Purchase Successful</h2>
                <p id='order-id'>Order ID: {order_id}</p>
                <p>A confirmation email has been sent.</p>
                <a href='/checkout' id='back-btn'>Back to Shop</a>
            </body></html>
            """)
            
        elif path == "/profile":
            address = params.get("address", [""])[0]
            self.send_response(303)
            self.send_header("Location", f"/profile?msg=Address+updated+to+{urllib.parse.quote(address)}")
            self.end_headers()
            
        elif path == "/contact":
            username = params.get("username", [""])[0]
            self.send_response(303)
            self.send_header("Location", f"/contact?msg=Message+from+{urllib.parse.quote(username)}+submitted")
            self.end_headers()
        else:
            self.send_html("404 Not Found", 404)

    # ── Page Rendering HTMLs ──────────────────────────────────────────────────

    def render_login(self, error):
        error_html = f"<p style='color:red;' id='error-msg'>{error}</p>" if error else ""
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Secure Login Portal</title></head>
        <body><main>
            <h2>Sign In</h2>
            {error_html}
            <form action="/login" method="post">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" placeholder="Username" required>
                <br>
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Password" required>
                <br>
                <button type="submit" id="login-btn">Sign In</button>
            </form>
            <p><a href="/forgot-password" id="forgot-password-link">Forgot Password?</a></p>
        </main></body></html>
        """)

    def render_2fa(self, username, error):
        error_html = f"<p style='color:red;' id='error-msg'>{error}</p>" if error else ""
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Two-Factor Authentication</title></head>
        <body><main>
            <h2>Verification Required</h2>
            <p>Please enter the security code for <strong>{username}</strong>.</p>
            {error_html}
            <form action="/2fa" method="post">
                <input type="hidden" name="username" value="{username}">
                <label for="otp">Security Code</label>
                <input type="text" id="otp" name="otp" placeholder="6-digit code" required autocomplete="off">
                <br>
                <button type="submit" id="verify-btn">Verify</button>
            </form>
        </main></body></html>
        """)

    def render_dashboard(self, token):
        if token in SESSIONS:
            self.send_html(f"""
            <!DOCTYPE html>
            <html><head><title>Dashboard</title></head>
            <body><main>
                <h1 id="welcome-header">Welcome to BrowserMind Dashboard</h1>
                <p id="session-token">Session token: {token}</p>
                <p>Status: Authenticated</p>
            </main></body></html>
            """)
        else:
            self.send_html("Unauthorized Session", 401)

    def render_forgot_password(self, error):
        error_html = f"<p style='color:red;' id='error-msg'>{error}</p>" if error else ""
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Forgot Password</title></head>
        <body><main>
            <h2>Account Recovery</h2>
            <p>Enter your username to recover your account.</p>
            {error_html}
            <form action="/forgot-password" method="post">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" placeholder="Username" required>
                <br>
                <button type="submit" id="recover-btn">Send Recovery Link</button>
            </form>
        </main></body></html>
        """)

    def render_reset_password(self, username, token):
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Reset Password</title></head>
        <body><main>
            <h2>Set New Password</h2>
            <p>Resetting password for <strong>{username}</strong> (token: {token}).</p>
            <form action="/reset-password" method="post">
                <input type="hidden" name="username" value="{username}">
                <label for="password">New Password</label>
                <input type="password" id="password" name="password" placeholder="New Password" required>
                <br>
                <button type="submit" id="submit-btn">Update Password</button>
            </form>
        </main></body></html>
        """)

    def render_vault(self, username):
        otp = VAULT_OTPS.get(username, "N/A")
        status_note = "EXPIRED" if otp == "000000" else "ACTIVE"
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Personal Password Manager (Vault)</title></head>
        <body><main>
            <h2>Credentials for {username}</h2>
            <div class="credentials-card">
                <p>Username: <span id="vault-user">{username}</span></p>
                <p>Password: <span id="vault-pass">{USERS.get(username, "N/A")}</span></p>
                <p>2FA Generator: <span id="otp-code">{otp}</span> (<span id="vault-status">{status_note}</span>)</p>
            </div>
        </main></body></html>
        """)

    def render_email_client(self, username):
        global RESET_TIME, EMAIL_DELAY
        import time
        if EMAIL_DELAY and (time.time() - RESET_TIME < 3.0):
            user_emails = []
        else:
            user_emails = EMAILS.get(username, [])
            
        emails_list_html = ""
        for i, m in enumerate(user_emails):
            emails_list_html += f"""
            <div class="email-item" style="border: 1px solid #ccc; padding: 10px; margin: 10px 0;">
                <h4 class="email-subject" id="subject-{i}">{m['subject']}</h4>
                <p class="email-body" id="body-{i}">{m['body']}</p>
            </div>
            """
        if not user_emails:
            emails_list_html = "<p id='no-emails'>Your inbox is empty.</p>"

        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Web Email Client</title></head>
        <body><main>
            <h2>Inbox for {username}@browsermind.local</h2>
            <div id="emails-container">
                {emails_list_html}
            </div>
        </main></body></html>
        """)

    def render_checkout(self):
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>BrowserMind Store Checkout</title></head>
        <body><main>
            <h2>Order Checkout</h2>
            <form action="/checkout" method="post">
                <label for="product">Product</label>
                <input type="text" id="product" name="product" value="BrowserMind Premium License" readonly>
                <br>
                <label for="quantity">Quantity</label>
                <input type="number" id="quantity" name="quantity" value="1" min="1" required>
                <br>
                <label for="address">Shipping Address</label>
                <input type="text" id="address" name="address" placeholder="123 AI Lane" required>
                <br>
                <label for="card">Credit Card Number</label>
                <input type="text" id="card" name="card" placeholder="1111-2222-3333-4444" required>
                <br>
                <button type="submit" id="purchase-btn">Purchase License</button>
            </form>
        </main></body></html>
        """)

    # ── Neutral / Controlled Local Endpoints ─────────────────────────────────

    def render_search(self, q):
        results_html = f"<p id='search-results'>Found 3 results for query '{q}'</p>" if q else "<p>Enter search query.</p>"
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Search Portal</title></head>
        <body><main>
            <h2>Search Information</h2>
            <form action="/search" method="get">
                <input type="text" id="query" name="q" placeholder="Enter query" value="{q}">
                <button type="submit" id="search-btn">Search</button>
            </form>
            {results_html}
        </main></body></html>
        """)

    def render_navigation(self, menu):
        msg = f"<p id='nav-status'>Menu item {menu} clicked</p>" if menu else "<p>Select menu item.</p>"
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Navigation Portal</title></head>
        <body><main>
            <h2>Menu Navigation</h2>
            <nav>
                <a href="/navigation?menu=1" id="nav-item-1">Item 1</a> |
                <a href="/navigation?menu=2" id="nav-item-2">Item 2</a> |
                <a href="/navigation?menu=3" id="nav-item-3">Item 3</a>
            </nav>
            {msg}
        </main></body></html>
        """)

    def render_filter(self, size):
        msg = f"<p id='filtered-results'>Showing 1 XS product</p>" if size == "xs" else "<p>Select size filter.</p>"
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Product Filtering</title></head>
        <body><main>
            <h2>Filter Products</h2>
            <form action="/filter" method="get">
                <input type="checkbox" id="size-xs" name="size" value="xs" {"checked" if size == "xs" else ""}> Size XS
                <input type="checkbox" id="size-s" name="size" value="s"> Size S
                <button type="submit" id="filter-btn">Apply Filter</button>
            </form>
            {msg}
        </main></body></html>
        """)

    def render_profile(self, msg):
        status = f"<p id='profile-status'>{msg}</p>" if msg else ""
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>User Profile</title></head>
        <body><main>
            <h2>Edit Profile Billing</h2>
            {status}
            <form action="/profile" method="post">
                <label for="address">Billing Address</label>
                <input type="text" id="address" name="address" placeholder="Billing Address">
                <button type="submit" id="submit-profile-btn">Update Profile</button>
            </form>
        </main></body></html>
        """)

    def render_contact(self, msg):
        status = f"<p id='contact-status'>{msg}</p>" if msg else ""
        self.send_html(f"""
        <!DOCTYPE html>
        <html><head><title>Contact Form</title></head>
        <body><main>
            <h2>Submit Contact Form</h2>
            {status}
            <form action="/contact" method="post">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" placeholder="Username">
                <button type="submit" id="submit-contact-btn">Submit Contact</button>
            </form>
        </main></body></html>
        """)


def start_server_in_background():
    import socketserver
    # Use standard TCPServer with reuse option
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("", PORT), MockAppHandler)
    import threading
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    return server
