from flask import Flask, request, jsonify
import requests
import threading
import time
import os
import json

app = Flask(__name__)

# ====================================
# ENVIRONMENT VARIABLES (Vercel pe set karna)
# ====================================
AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
DEVICE_ID = os.environ.get('DEVICE_ID')
USER_AGENT = os.environ.get('USER_AGENT')
API_HOST = os.environ.get('API_HOST', 'https://westeros.famapp.in')

# Cache file
CACHE_FILE = "cache.json"

# ====================================
# VALIDATE ENVIRONMENT
# ====================================
def check_env():
    """Check if required environment variables are set"""
    missing = []
    if not AUTH_TOKEN:
        missing.append('AUTH_TOKEN')
    if not DEVICE_ID:
        missing.append('DEVICE_ID')
    if not USER_AGENT:
        missing.append('USER_AGENT')
    
    return missing

# ====================================
# CACHE SYSTEM
# ====================================
def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                
                # Clean old entries (24 hours)
                current = time.time()
                cleaned = {}
                for key, val in cache.items():
                    if current - val.get('time', 0) < 86400:
                        cleaned[key] = val
                
                if len(cleaned) != len(cache):
                    save_cache(cleaned)
                
                return cleaned
    except:
        return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except:
        pass

def get_cached(fam_id):
    cache = load_cache()
    if fam_id in cache:
        data = cache[fam_id]
        if time.time() - data['time'] < 86400:
            return data
        else:
            del cache[fam_id]
            save_cache(cache)
    return None

def add_cache(fam_id, phone, name):
    cache = load_cache()
    cache[fam_id] = {'phone': phone, 'name': name, 'time': time.time()}
    
    # Keep only 500 entries max
    if len(cache) > 500:
        cache = dict(list(cache.items())[-500:])
    
    save_cache(cache)

# ====================================
# API FUNCTIONS
# ====================================
def create_session():
    session = requests.Session()
    session.headers.update({
        "host": "westeros.famapp.in",
        "user-agent": USER_AGENT,
        "x-device-details": USER_AGENT,
        "x-app-version": "525",
        "x-platform": "1",
        "device-id": DEVICE_ID,
        "authorization": f"Token {AUTH_TOKEN}",
        "accept-encoding": "gzip",
        "content-type": "application/json; charset=UTF-8"
    })
    return session

def unblock_bg(session, fam_id):
    def task():
        try:
            time.sleep(1)
            session.post(
                f"{API_HOST}/user/vpa/block/",
                json={"block": False, "vpa": fam_id}
            )
        except:
            pass
    threading.Thread(target=task).start()

# ====================================
# ROUTES
# ====================================
@app.route('/')
def home():
    missing = check_env()
    
    if missing:
        return jsonify({
            "error": f"Missing environment variables: {', '.join(missing)}",
            "instructions": "Set AUTH_TOKEN, DEVICE_ID, USER_AGENT on Vercel"
        }), 500
    
    cache = load_cache()
    return jsonify({
        "app": "FamPay Lookup",
        "status": "active",
        "cache_entries": len(cache),
        "usage": "/get?id=username@fam"
    })

@app.route('/get')
def get_number():
    # Check env first
    missing = check_env()
    if missing:
        return jsonify({
            "error": f"Server not configured. Missing: {', '.join(missing)}"
        }), 500
    
    fam_id = request.args.get('id', '').strip()
    
    if not fam_id:
        return jsonify({"error": "Send ?id=username@fam"}), 400
    
    if not fam_id.endswith('@fam'):
        return jsonify({"error": "Invalid format. Use username@fam"}), 400
    
    # Check cache
    cached = get_cached(fam_id)
    if cached:
        return jsonify({
            "success": True,
            "fam_id": fam_id,
            "name": cached['name'],
            "phone": cached['phone'],
            "cached": True
        })
    
    try:
        session = create_session()
        
        # Block user
        block_res = session.post(
            f"{API_HOST}/user/vpa/block/",
            json={"block": True, "vpa": fam_id}
        )
        
        if block_res.status_code != 200:
            return jsonify({
                "error": f"Block failed: {block_res.status_code}",
                "fam_id": fam_id
            }), 400
        
        # Get blocked list
        list_res = session.get(f"{API_HOST}/user/blocked_list/")
        
        if list_res.status_code == 200:
            data = list_res.json()
            if data.get('results'):
                user = data['results'][0]
                contact = user.get('contact', {})
                
                result = {
                    "success": True,
                    "fam_id": fam_id,
                    "name": contact.get('name', ''),
                    "phone": contact.get('phone_number', ''),
                    "cached": False
                }
                
                # Save to cache
                if result['phone']:
                    add_cache(fam_id, result['phone'], result['name'])
                
                # Unblock
                unblock_bg(session, fam_id)
                
                return jsonify(result)
        
        return jsonify({
            "success": False,
            "error": "User not found",
            "fam_id": fam_id
        }), 404
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "fam_id": fam_id
        }), 500

@app.route('/cache')
def cache_info():
    cache = load_cache()
    return jsonify({
        "entries": len(cache),
        "keys": list(cache.keys())[:20]
    })

@app.route('/clear', methods=['POST'])
def clear_cache():
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

@app.route('/env')
def env_check():
    """Debug endpoint to check environment (remove in production)"""
    return jsonify({
        "AUTH_TOKEN_set": bool(AUTH_TOKEN),
        "DEVICE_ID_set": bool(DEVICE_ID),
        "USER_AGENT_set": bool(USER_AGENT),
        "API_HOST": API_HOST
    })

# ====================================
# RUN
# ====================================
if __name__ == '__main__':
    app.run(debug=True)