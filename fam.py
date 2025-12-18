from flask import Flask, request, jsonify
import requests
import threading
import time
import os

app = Flask(__name__)

# ====================================
# ENVIRONMENT VARIABLES
# ====================================
AUTH_TOKEN = os.environ.get('AUTH_TOKEN')
DEVICE_ID = os.environ.get('DEVICE_ID')
USER_AGENT = os.environ.get('USER_AGENT')
API_HOST = os.environ.get('API_HOST', 'https://westeros.famapp.in')

# ====================================
# IN-MEMORY CACHE (No file needed)
# ====================================
cache = {}
CACHE_EXPIRY = 86400  # 24 hours

def get_cached(fam_id):
    """Get from memory cache"""
    if fam_id in cache:
        entry = cache[fam_id]
        if time.time() - entry['time'] < CACHE_EXPIRY:
            return entry
        else:
            del cache[fam_id]
    return None

def add_cache(fam_id, phone, name):
    """Add to memory cache"""
    cache[fam_id] = {
        'phone': phone,
        'name': name,
        'time': time.time()
    }
    
    # Keep only 100 entries max
    if len(cache) > 100:
        # Remove oldest entry
        oldest_key = min(cache.keys(), key=lambda k: cache[k]['time'])
        del cache[oldest_key]

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
    missing = []
    if not AUTH_TOKEN: missing.append('AUTH_TOKEN')
    if not DEVICE_ID: missing.append('DEVICE_ID')
    if not USER_AGENT: missing.append('USER_AGENT')
    
    if missing:
        return jsonify({
            "error": f"Missing: {', '.join(missing)}"
        }), 500
    
    return jsonify({
        "app": "FamPay Lookup",
        "status": "active",
        "cache_entries": len(cache),
        "cache_type": "in-memory",
        "usage": "/get?id=username@fam"
    })

@app.route('/get')
def get_number():
    # Check env
    if not AUTH_TOKEN or not DEVICE_ID or not USER_AGENT:
        return jsonify({"error": "Server not configured"}), 500
    
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
            "cached": True,
            "cache_entries": len(cache)
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
    """Show cache contents"""
    entries = []
    current_time = time.time()
    
    for fam_id, data in cache.items():
        age = current_time - data['time']
        expires_in = CACHE_EXPIRY - age
        
        entries.append({
            "fam_id": fam_id,
            "name": data['name'],
            "phone": "****" + data['phone'][-4:] if data['phone'] else "",
            "age_hours": round(age/3600, 1),
            "expires_in_hours": round(max(0, expires_in/3600), 1)
        })
    
    # Sort by newest
    entries.sort(key=lambda x: x['age_hours'])
    
    return jsonify({
        "total": len(entries),
        "cache_type": "in-memory",
        "max_age_hours": 24,
        "entries": entries[:20]  # Show first 20
    })

@app.route('/clear', methods=['POST'])
def clear_cache():
    """Clear memory cache"""
    global cache
    cache.clear()
    return jsonify({
        "success": True,
        "message": "Cache cleared",
        "entries_cleared": len(cache)
    })

@app.route('/env')
def env_check():
    return jsonify({
        "AUTH_TOKEN_set": bool(AUTH_TOKEN),
        "DEVICE_ID_set": bool(DEVICE_ID),
        "USER_AGENT_set": bool(USER_AGENT),
        "cache_size": len(cache)
    })

# ====================================
# RUN
# ====================================
if __name__ == '__main__':
    app.run(debug=True)