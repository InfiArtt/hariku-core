# Hariku V2 — accessible calendar & automation for screen-reader users.
# Copyright (C) 2024-2026 InfiArtt (Rafli) and Hariku contributors.
#
# This file is part of Hariku, released under the GNU General Public License,
# version 3 or (at your option) any later version, with the Hariku Extension
# Exception. See LICENSE and LICENSE-EXCEPTION. Distributed WITHOUT ANY WARRANTY.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Exists solely to tell Nuitka to bundle these Python standard-library modules
# into the .exe. External extensions (e.g. wikipedia_reader) import them
# dynamically, so without importing them here Nuitka would strip them out to
# save space.

import socket
import ssl
import json
import sqlite3
import urllib.request
import urllib.parse
import urllib.error
import http.client
import http.server
import http.cookies
import http.cookiejar
import xml.etree.ElementTree
import html.parser
import html.entities
import datetime
import time
import math
import re
import threading
import subprocess
import os
import sys
import uuid
import base64
import hashlib
import csv
import io
import fractions
import decimal
import string
import random
import shlex        # Routines "open app" action
import pydoc        # Developer Toolkit
import zoneinfo     # World Clock (zone data comes from tzdata, below)

try:
    import cryptography
    from cryptography import fernet
except ImportError:
    pass

# The IANA zone database. Windows has none built in, so zoneinfo needs this
# package; release.yml also bundles its data files (--include-package-data).
try:
    import tzdata
except ImportError:
    pass

try:
    import wx.stc   # Developer Toolkit's code editor
except ImportError:
    pass

# tests/test_extension_stdlib.py fails when an extension imports a module that
# neither the core nor this file brings into the build.
