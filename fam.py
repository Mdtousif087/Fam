from flask import Flask, request, jsonify
import requests
import threading
import time
import os
import json

app = Flask(__name__)

# ====================================
# ENVIRONMENT VARIABLES (Vercel pe set karna hai)
# ====================================
AUTH_TOKEN = os.environ.get('AUTH_TOKEN', 'eyJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwiZXBrIjp7Imt0eSI6Ik9LUCIsImNydiI6Ilg0NDgiLCJ4IjoiQ05iRHkxQmxBUUVpOVlPYmItdlM2TklxUldiNkJ1VFd3d1pZNkx2MlM2QlI2UWM0c2h2dzh4X2tLcVZwWnFheFNkbWpXZ0Jrd3JZIn0sImFsZyI6IkVDREgtRVMifQ..azn1X3QVPLXmYtS5WnTF5g.WK4YgAn8pxf7aMDLN-tUVoID5EabXAyTEfhIQ_GG7znJ3_ezx5u_c2tBFzeaIFs5bWxB0epa0ucwuYiIeseBpyppkGwNQthyyeh7OLEwj67gCVEEz0wYGOpGAMxs6hijNNR34scAAtB2SIgLONbqGoPIWAgxfaxuNsPbmtTLMIkPjbgXqK-Rr9Ju6aFZ7lMDLz2MOMF5BfH_PkH2pMu9YH-oxS3aqSQEYmz2rX1Z6SybjdVojvB7zBqrpuSQkiykPjNRpNMszlRLqsrPax-BG5b5yryuX_SVN730Z1s4uWSUOHJW0wACX7St1tSxbx2z5E3sLo9DwYOg9MKIq3sQwzfKmsKBcIg2n_IYhROXHM1P6z_yoSuIx1GBNafgndHw.n0jZJ9yQDCu_rdsg36eOgj-UoS3nWDLpsU0KbMU-6TE')
DEVICE_ID = os.environ.get('DEVICE_ID', 'adb84e9925c4f17a')
USER_AGENT = os.environ.get('USER_AGENT', '2312DRAABI | Android 15 | Dalvik/2.1.0 | gold | 2EF4F924D8CD3764269BD3548C4E7BF4FA070E7B | 3.11.5 (Build 525) | U78TN5J23U')
API_HOST = os.environ.get('API_HOST', 'https://westeros.famapp.in')

# Cache settings
CACHE_FILE = "cache.json"
CACHE_EXPIRY = 86400  # 24 hours in seconds

# ====================================
# CACHE SYSTEM
# ====================================
def load_cache():
    """Load cache from JSON file"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
                # Clean expired entries
                current_time = time.time()
                cleaned_cache = {}
                
                for fam_id, entry in cache_data.items():
                    entry_time = entry.get('timestamp', 0)
                    if current_time - entry_time < CACHE_EXPIRY:
                        cleaned_cache[fam_id] = entry
                
                # Save cleaned cache back
                if len(cleaned_cache) != len(cache_data):
                    save_cache(cleaned_cache)
                
                return cleaned_cache
    except Exception as e:
        print(f"[CACHE ERROR] Load: {e}")
    return {}

def save_cache(cache_data):
    """Save cache to JSON file"""
    try:
        # Keep only last 500 entries to prevent large file
        if len(cache_data) > 500:
            cache_data = dict(list(cache_data.items())[-500:])
        
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CACHE ERROR] Save: {e}")

def get_from_cache(fam_id):
    """Get entry from cache if exists and not expired"""
    cache_data = load_cache()
    
    if fam_id in cache_data:
        entry = cache_data[fam_id]
        current_time = time.time()
        
        # Check if entry is still valid (less than 24 hours old)
        if current_time - entry.get('timestamp', 0) < CACHE_EXPIRY:
            return {
                'status': True,
                'fam_id': fam_id,
                'name': entry.get('name', ''),
                'phone': entry.get('phone', ''),
                'from_cache': True,
                'timestamp': entry.get('timestamp', 0)
            }
        else:
            # Remove expired entry
            del cache_data[fam_id]
            save_cache(cache_data)
    
    return None

def add_to_cache(fam_id, phone, name):
    """Add new entry to cache"""
    cache_data = load_cache()
    
    cache_data[fam_id] = {
        'phone': phone,
        'name': name,
        'timestamp': time.time()
    }
    
    save_cache(cache_data)
    print(f"[CACHE] Added {fam_id} -> {phone}")

# ====================================
# SESSION & API FUNCTIONS
# ====================================
def create_session():
    """Create requests session with proper headers"""
    session = requests.Session()
    
    # ALL HEADERS INCLUDED
    session.headers.update({
        "Host": "westeros.famapp.in",
        "User-Agent": USER_AGENT,
        "X-Device-Details": USER_AGENT,
        "X-App-Version": "525",
        "X-Platform": "1",
        "Device-Id": DEVICE_ID,
        "Authorization": f"Token {AUTH_TOKEN}",
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json; charset=UTF-8"
    })
    
    return session

def fetch_blocked_list(session):
    """Fetch current blocked list"""
    try:
        response = session.get(
            f"{API_HOST}/user/blocked_list/",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[API ERROR] Blocked list: {e}")
    return None

def block_user(session, fam_id):
    """Block a user"""
    try:
        response = session.post(
            f"{API_HOST}/user/vpa/block/",
            json={"block": True, "vpa": fam_id},
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[API ERROR] Block: {e}")
    return False

def unblock_user(session, fam_id):
    """Unblock a user (in background thread)"""
    def unblock_task():
        try:
            time.sleep(1)  # Wait 1 second
            session.post(
                f"{API_HOST}/user/vpa/block/",
                json={"block": False, "vpa": fam_id},
                timeout=5
            )
            print(f"[UNBLOCK] Success: {fam_id}")
        except:
            pass
    
    # Start in background thread
    threading.Thread(target=unblock_task, daemon=True).start()

# ====================================
# FLASK ROUTES
# ====================================
@app.route('/')
def home():
    """Home page with info"""
    cache_data = load_cache()
    
    return jsonify({
        'app': 'FamPay ID Lookup API',
        'version': '2.0',
        'author': 'Your Name',
        'endpoints': {
            'get_number': '/get?id=username@fam',
            'cache_info': '/cache',
            'clear_cache': '/clear (POST)',
            'health': '/health'
        },
        'cache': {
            'entries': len(cache_data),
            'file': CACHE_FILE,
            'expiry_hours': 24
        },
        'env_status': {
            'AUTH_TOKEN_set': bool(AUTH_TOKEN),
            'DEVICE_ID_set': bool(DEVICE_ID),
            'USER_AGENT_set': bool(USER_AGENT)
        }
    })

@app.route('/get', methods=['GET'])
def get_number():
    """Main endpoint to get phone number from Fam ID"""
    # Get Fam ID from query parameter
    fam_id = request.args.get('id', '').strip()
    
    # Validate input
    if not fam_id:
        return jsonify({
            'success': False,
            'error': 'Missing Fam ID. Use: /get?id=username@fam'
        }), 400
    
    if not fam_id.endswith('@fam'):
        return jsonify({
            'success': False,
            'error': 'Invalid Fam ID format. Must end with @fam'
        }), 400
    
    print(f"[REQUEST] Looking up: {fam_id}")
    
    # STEP 1: Check cache first
    cached_result = get_from_cache(fam_id)
    if cached_result:
        print(f"[CACHE HIT] Returning cached data for {fam_id}")
        return jsonify(cached_result)
    
    print(f"[CACHE MISS] Cache miss for {fam_id}")
    
    # STEP 2: Validate environment variables
    if not AUTH_TOKEN or not DEVICE_ID:
        return jsonify({
            'success': False,
            'error': 'Server not configured properly',
            'fam_id': fam_id
        }), 500
    
    # STEP 3: Create session and make API calls
    session = create_session()
    
    try:
        # First, check if already in blocked list
        blocked_data = fetch_blocked_list(session)
        
        if blocked_data and blocked_data.get('results'):
            # Search in existing blocked list
            for user in blocked_data['results']:
                if user and user.get('contact'):
                    contact = user['contact']
                    name = contact.get('name', '').lower()
                    fam_id_clean = fam_id.replace('@fam', '').lower()
                    
                    # Check if this is our user
                    if fam_id_clean in name:
                        result = {
                            'success': True,
                            'fam_id': fam_id,
                            'name': contact.get('name', ''),
                            'phone': contact.get('phone_number', ''),
                            'from_cache': False,
                            'source': 'existing_blocked_list'
                        }
                        
                        # Save to cache
                        if result['phone']:
                            add_to_cache(fam_id, result['phone'], result['name'])
                        
                        # Unblock user
                        unblock_user(session, fam_id)
                        
                        return jsonify(result)
        
        # STEP 4: Block user to get info
        print(f"[API] Blocking user: {fam_id}")
        block_success = block_user(session, fam_id)
        
        if not block_success:
            return jsonify({
                'success': False,
                'error': 'Failed to block user',
                'fam_id': fam_id
            }), 500
        
        # STEP 5: Get updated blocked list
        updated_data = fetch_blocked_list(session)
        
        if not updated_data or not updated_data.get('results'):
            return jsonify({
                'success': False,
                'error': 'No data received from API',
                'fam_id': fam_id
            }), 500
        
        # Get the first (newest) user from list
        if updated_data['results']:
            newest_user = updated_data['results'][0]
            
            if newest_user and newest_user.get('contact'):
                contact = newest_user['contact']
                
                result = {
                    'success': True,
                    'fam_id': fam_id,
                    'name': contact.get('name', ''),
                    'phone': contact.get('phone_number', ''),
                    'from_cache': False,
                    'source': 'fresh_block'
                }
                
                # Save to cache
                if result['phone']:
                    add_to_cache(fam_id, result['phone'], result['name'])
                
                # Unblock user in background
                unblock_user(session, fam_id)
                
                return jsonify(result)
        
        return jsonify({
            'success': False,
            'error': 'User not found',
            'fam_id': fam_id
        }), 404
        
    except Exception as e:
        print(f"[ERROR] Exception: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'fam_id': fam_id
        }), 500

@app.route('/cache', methods=['GET'])
def cache_info():
    """Get cache information"""
    cache_data = load_cache()
    
    entries = []
    current_time = time.time()
    
    for fam_id, entry in cache_data.items():
        age_hours = (current_time - entry.get('timestamp', 0)) / 3600
        expires_in = 24 - age_hours
        
        entries.append({
            'fam_id': fam_id,
            'name': entry.get('name', ''),
            'phone': entry.get('phone', '')[:3] + '****' + entry.get('phone', '')[-3:] if entry.get('phone') else '',
            'age_hours': round(age_hours, 1),
            'expires_in_hours': round(max(0, expires_in), 1)
        })
    
    # Sort by newest first
    entries.sort(key=lambda x: x['age_hours'])
    
    return jsonify({
        'success': True,
        'total_entries': len(entries),
        'cache_file': CACHE_FILE,
        'expiry_hours': 24,
        'entries': entries[:50]  # Show first 50 only
    })

@app.route('/clear', methods=['POST'])
def clear_cache():
    """Clear cache file"""
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            return jsonify({
                'success': True,
                'message': 'Cache cleared successfully'
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Cache file does not exist'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    cache_data = load_cache()
    
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'cache': {
            'file_exists': os.path.exists(CACHE_FILE),
            'entries': len(cache_data)
        },
        'environment': {
            'AUTH_TOKEN_configured': bool(AUTH_TOKEN),
            'DEVICE_ID_configured': bool(DEVICE_ID),
            'USER_AGENT_configured': bool(USER_AGENT)
        }
    })

# ====================================
# START APPLICATION
# ====================================
if __name__ == '__main__':
    # For local testing
    print("=" * 50)
    print("🚀 FamPay Lookup API Starting...")
    print("=" * 50)
    print(f"📁 Cache File: {CACHE_FILE}")
    print(f"🔑 AUTH_TOKEN: {'✓ Set' if AUTH_TOKEN else '✗ Missing'}")
    print(f"📱 DEVICE_ID: {'✓ Set' if DEVICE_ID else '✗ Missing'}")
    print(f"🌐 API_HOST: {API_HOST}")
    print("=" * 50)
    print("🌍 Server running on http://127.0.0.1:5000")
    print("📌 Usage: http://127.0.0.1:5000/get?id=username@fam")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
