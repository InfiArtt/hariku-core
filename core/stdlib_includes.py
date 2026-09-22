# hariku2/core/stdlib_includes.py
# File ini berfungsi semata-mata untuk memberi tahu Nuitka agar membungkus
# modul-modul bawaan Python ke dalam .exe. Ekstensi eksternal (seperti 
# wikipedia_reader) memanggil modul ini secara dinamis, sehingga jika tidak
# kita import di sini, Nuitka akan membuangnya (stripping) untuk menghemat ruang.

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

try:
    import cryptography
    from cryptography import fernet
except ImportError:
    pass
