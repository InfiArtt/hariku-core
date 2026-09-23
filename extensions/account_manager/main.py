# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import wx
import json
import logging
import requests
import webbrowser
import base64
import hashlib
import os

import core.api
from core.events import bus
import auth_server

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
EXTENSION_ID = "account_manager"
# NOTE: this CLIENT_ID (and the redirect URI below) must be registered on the
# InfiArtt backend under /admin/oauth-clients for the OAuth flow to succeed.
CLIENT_ID = "a1978d33d5d59559a07d9e730f17a3af"
BASE_URL = "https://infiartt.com"
LOCAL_PORT = 16623
REDIRECT_URI = f"http://localhost:{LOCAL_PORT}/callback"
# ==============================================================================

def generate_pkce_pair():
    """Generates a random code_verifier and its SHA256 code_challenge."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('ascii')).digest()).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


class AccountSettingsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        
        # Load existing data
        self.data = core.api.load_data(EXTENSION_ID)
        self.access_token = self.data.get("access_token")
        self.user_profile = self.data.get("user_profile")
        
        self.setup_ui()
        
    def setup_ui(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(self, label="Hariku Cloud Account")
        title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.sizer.Add(title, 0, wx.ALL, 10)
        
        info_text = wx.StaticText(self, label="Login to sync your data and access cloud features.")
        self.sizer.Add(info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Status Area
        self.status_box = wx.StaticBox(self, label="Account Status")
        status_sizer = wx.StaticBoxSizer(self.status_box, wx.VERTICAL)
        
        self.lbl_status = wx.StaticText(self, label="")
        self.lbl_roles = wx.StaticText(self, label="")
        
        status_sizer.Add(self.lbl_status, 0, wx.ALL, 5)
        status_sizer.Add(self.lbl_roles, 0, wx.ALL, 5)
        
        self.sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_login = wx.Button(self, label="Login with Passkey / 2FA")
        self.btn_login.Bind(wx.EVT_BUTTON, self.on_login_clicked)
        
        self.btn_logout = wx.Button(self, label="Logout")
        self.btn_logout.Bind(wx.EVT_BUTTON, self.on_logout_clicked)
        
        btn_sizer.Add(self.btn_login, 0, wx.RIGHT, 10)
        btn_sizer.Add(self.btn_logout, 0)
        
        self.sizer.Add(btn_sizer, 0, wx.ALL, 10)
        self.SetSizer(self.sizer)
        
        self.update_ui_state()
        
    def update_ui_state(self):
        if self.access_token and self.user_profile:
            username = self.user_profile.get("username", "Unknown")
            roles = ", ".join(self.user_profile.get("roles", []))
            
            self.lbl_status.SetLabel(f"Logged in as: {username}")
            self.lbl_roles.SetLabel(f"Roles: {roles}")
            
            self.btn_login.Disable()
            self.btn_logout.Enable()
        else:
            self.lbl_status.SetLabel("Status: Not logged in")
            self.lbl_roles.SetLabel("")
            
            self.btn_login.Enable()
            self.btn_logout.Disable()
            
        self.Layout()

    def on_login_clicked(self, event):
        self.btn_login.Disable()
        self.lbl_status.SetLabel("Status: Waiting for browser login...")
        
        # Run OAuth flow in background thread so UI doesn't freeze
        core.api.run_thread(self.run_oauth_flow, self.on_oauth_finished)
        
    def run_oauth_flow(self):
        try:
            # 1. PKCE Setup
            code_verifier, code_challenge = generate_pkce_pair()
            
            # 2. Open Browser
            auth_url = (f"{BASE_URL}/oauth/authorize?client_id={CLIENT_ID}"
                        f"&redirect_uri={REDIRECT_URI}&response_type=code"
                        f"&code_challenge={code_challenge}&code_challenge_method=S256")
            
            logger.info("Opening browser for OAuth login...")
            webbrowser.open(auth_url)
            
            # 3. Wait for Local Server Callback (Blocking in this thread)
            auth_code = auth_server.wait_for_auth_code(LOCAL_PORT)
            
            if auth_code == "ERROR" or not auth_code:
                return {"error": "Login cancelled or failed."}
                
            # 4. Exchange Code for Token (Using PKCE, no client_secret needed!)
            logger.info("Exchanging code for token...")
            token_resp = requests.post(
                f"{BASE_URL}/oauth/token",
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": code_verifier
                },
                timeout=10
            )
            
            if token_resp.status_code != 200:
                return {"error": f"Token exchange failed: {token_resp.text}"}
                
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                return {"error": "No access token received."}
                
            # 5. Fetch User Profile
            logger.info("Fetching user profile...")
            api_resp = requests.get(
                f"{BASE_URL}/api/user",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            
            if api_resp.status_code != 200:
                return {"error": "Failed to fetch user profile."}
                
            user_profile = api_resp.json()
            
            return {
                "success": True,
                "access_token": access_token,
                "user_profile": user_profile
            }
            
        except Exception as e:
            logger.error(f"OAuth flow error: {e}")
            return {"error": str(e)}

    def on_oauth_finished(self, result):
        if not result:
            core.api.show_toast("Login Error", "An unknown error occurred during login.", flags=wx.ICON_ERROR)
            self.update_ui_state()
            return
            
        if "error" in result:
            core.api.show_toast("Login Failed", result["error"], flags=wx.ICON_ERROR)
            self.update_ui_state()
            return
            
        # Success!
        self.access_token = result["access_token"]
        self.user_profile = result["user_profile"]
        
        # Save to storage
        self.data["access_token"] = self.access_token
        self.data["user_profile"] = self.user_profile
        core.api.save_data(EXTENSION_ID, self.data)
        
        # Also expose globally for other extensions to easily grab
        # Using a convention of setting it to core.api or emitting an event
        
        self.update_ui_state()
        core.api.show_toast("Login Success", f"Welcome back, {self.user_profile.get('username')}!", flags=wx.ICON_INFORMATION)
        
        # Broadcast event to other extensions
        bus.emit("on_user_login", {"profile": self.user_profile, "token": self.access_token})

    def on_logout_clicked(self, event):
        self.access_token = None
        self.user_profile = None
        self.data = {}
        core.api.save_data(EXTENSION_ID, self.data)
        self.update_ui_state()
        
        core.api.show_toast("Logout", "You have been securely logged out.", flags=wx.ICON_INFORMATION)
        bus.emit("on_user_logout")


def on_app_startup():
    """When the app starts, let's load our data and broadcast if we are logged in."""
    data = core.api.load_data(EXTENSION_ID)
    access_token = data.get("access_token")
    user_profile = data.get("user_profile")
    
    if access_token and user_profile:
        logger.info(f"[Account Manager] User {user_profile.get('username')} is logged in.")
        core.api.set_timeout(2000, lambda: bus.emit("on_user_login", {"profile": user_profile, "token": access_token}))

import core.preferences

def create_settings_panel(parent):
    return AccountSettingsPanel(parent)

def register(event_bus):
    """Called by Hariku Core when loading the extension."""
    core.preferences.register_panel("Account", "Hariku Cloud", create_settings_panel)
    event_bus.subscribe("on_app_startup", on_app_startup)
