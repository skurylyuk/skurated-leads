import streamlit as st
import psycopg2
import pandas as pd
import requests
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
APP_PASSWORD = "skurated2024"
APOLLO_API_KEY = "kLPqt3p8rIR_2i4CrTSjNw"
APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
MONTHLY_CREDITS = 120

DB_CONFIG = {
    "host": "aws-1-us-east-2.pooler.supabase.com",
    "port": "6543",
    "database": "postgres",
    "user": "postgres.xqqetwvytmevetjixxxq",
    "password": "YZqaXRbu-b7KFb8"
}

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="SKurated B2B Pipeline",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    /* Main styling */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    .metric-card.credits {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .metric-card.pending {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    .metric-card.unlocked {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    .metric-card.emailed {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
    }
    .metric-card.responded {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        color: #333;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
        margin-top: 0.5rem;
    }
    
    /* Status badges */
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
    }
    .status-pending { background: #fff3cd; color: #856404; }
    .status-unlocked { background: #cce5ff; color: #004085; }
    .status-emailed { background: #d4edda; color: #155724; }
    .status-responded { background: #d1ecf1; color: #0c5460; }
    
    /* Lead card */
    .lead-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: all 0.2s ease;
    }
    .lead-card:hover {
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        transform: translateY(-2px);
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Mobile responsive */
    @media (max-width: 768px) {
        .metric-value { font-size: 1.8rem; }
        .main-header { font-size: 1.5rem; }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# DATABASE FUNCTIONS
# ============================================================
@st.cache_resource
def get_db_connection():
    """Create and return a database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def execute_query(query, params=None, fetch=True):
    """Execute a database query."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        # Create a new cursor for each query
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            columns = [desc[0] for desc in cur.description]
            results = cur.fetchall()
            cur.close()
            return pd.DataFrame(results, columns=columns)
        else:
            conn.commit()
            cur.close()
            return True
    except Exception as e:
        conn.rollback()
        st.error(f"Query failed: {e}")
        return None

def get_all_leads():
    """Fetch all leads from the database."""
    query = """
        SELECT *
        FROM leads
        ORDER BY created_at DESC
    """
    return execute_query(query)

def get_lead_stats():
    """Get lead statistics."""
    query = """
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'pending_review') as pending,
            COUNT(*) FILTER (WHERE status = 'unlocked') as unlocked,
            COUNT(*) FILTER (WHERE status = 'emailed') as emailed,
            COUNT(*) FILTER (WHERE status = 'responded') as responded,
            COUNT(*) FILTER (WHERE credits_used = true) as credits_used
        FROM leads
    """
    return execute_query(query)

def update_lead(lead_id, updates):
    """Update a lead record."""
    set_clause = ", ".join([f'"{k}" = %s' for k in updates.keys()])
    query = f"UPDATE leads SET {set_clause} WHERE id = %s"
    params = list(updates.values()) + [lead_id]
    return execute_query(query, params, fetch=False)

def get_lead_by_id(lead_id):
    """Fetch a single lead by ID."""
    query = "SELECT * FROM leads WHERE id = %s"
    return execute_query(query, (lead_id,))

# ============================================================
# APOLLO API FUNCTIONS
# ============================================================
def unlock_email_apollo(apollo_id):
    """Call Apollo API to unlock an email."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": APOLLO_API_KEY
    }
    payload = {
        "id": apollo_id,
        "reveal_personal_emails": True
    }
    
    try:
        response = requests.post(APOLLO_MATCH_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Extract email from response
        person = data.get("person", {})
        email = person.get("email") or person.get("personal_email")
        
        return {"success": True, "email": email, "data": data}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "selected_lead" not in st.session_state:
    st.session_state.selected_lead = None
if "view" not in st.session_state:
    st.session_state.view = "dashboard"

# ============================================================
# LOGIN PAGE
# ============================================================
def show_login():
    st.markdown('<p class="main-header">🎯 SKurated B2B Pipeline</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Lead Management Dashboard</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Sign In")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", type="primary", use_container_width=True):
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid password")

# ============================================================
# DASHBOARD VIEW
# ============================================================
def show_dashboard():
    stats = get_lead_stats()
    if stats is None or stats.empty:
        st.warning("Unable to load statistics")
        return
    
    stats = stats.iloc[0]
    credits_remaining = MONTHLY_CREDITS - int(stats['credits_used'] or 0)
    
    # Header
    st.markdown('<p class="main-header">🎯 SKurated B2B Pipeline</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Lead Management Dashboard</p>', unsafe_allow_html=True)
    
    # Metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card credits">
            <div class="metric-value">{credits_remaining}</div>
            <div class="metric-label">Credits Remaining</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(stats['total'])}</div>
            <div class="metric-label">Total Leads</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card pending">
            <div class="metric-value">{int(stats['pending'] or 0)}</div>
            <div class="metric-label">Pending Review</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card unlocked">
            <div class="metric-value">{int(stats['unlocked'] or 0)}</div>
            <div class="metric-label">Unlocked</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        st.markdown(f"""
        <div class="metric-card emailed">
            <div class="metric-value">{int(stats['emailed'] or 0)}</div>
            <div class="metric-label">Emailed</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Quick actions
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📋 View All Leads", use_container_width=True):
            st.session_state.view = "leads"
            st.rerun()
    with col2:
        if st.button("⏳ Pending Review", use_container_width=True):
            st.session_state.view = "leads"
            st.session_state.filter_status = "pending_review"
            st.rerun()

# ============================================================
# LEADS TABLE VIEW
# ============================================================
def show_leads():
    st.markdown('<p class="main-header">📋 Lead Management</p>', unsafe_allow_html=True)
    
    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        search = st.text_input("🔍 Search", placeholder="Search by name or company...")
    
    with col2:
        status_filter = st.selectbox(
            "Status Filter",
            ["All", "pending_review", "unlocked", "emailed", "responded"],
            index=0 if "filter_status" not in st.session_state else 
                  ["All", "pending_review", "unlocked", "emailed", "responded"].index(
                      st.session_state.get("filter_status", "All")
                  )
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()
    
    # Clear filter status from session after using it
    if "filter_status" in st.session_state:
        del st.session_state.filter_status
    
    # Fetch leads
    leads_df = get_all_leads()
    
    if leads_df is None or leads_df.empty:
        st.info("No leads found in the database.")
        return
    
    # Apply filters
    filtered_df = leads_df.copy()
    
    if search:
        search_lower = search.lower()
        filtered_df = filtered_df[
            filtered_df['firstName'].fillna('').str.lower().str.contains(search_lower) |
            filtered_df['lastName'].fillna('').str.lower().str.contains(search_lower) |
            filtered_df['companyName'].fillna('').str.lower().str.contains(search_lower)
        ]
    
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    
    st.markdown(f"**Showing {len(filtered_df)} leads**")
    st.markdown("---")
    
    # Display leads
    for idx, lead in filtered_df.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                name = f"{lead['firstName'] or ''} {lead['lastName'] or ''}".strip()
                st.markdown(f"**{name}**")
                st.caption(f"{lead['jobTitle'] or 'N/A'}")
            
            with col2:
                st.markdown(f"🏢 {lead['companyName'] or 'N/A'}")
                st.caption(f"📍 {lead['location'] or 'N/A'}")
            
            with col3:
                status = lead['status'] or 'pending_review'
                status_colors = {
                    'pending_review': '🟡',
                    'unlocked': '🔵',
                    'emailed': '🟢',
                    'responded': '✅'
                }
                st.markdown(f"{status_colors.get(status, '⚪')} {status.replace('_', ' ').title()}")
                if lead['ai_score']:
                    st.caption(f"AI Score: {lead['ai_score']}/100")
            
            with col4:
                if st.button("View Details", key=f"view_{lead['id']}"):
                    st.session_state.selected_lead = lead['id']
                    st.session_state.view = "detail"
                    st.rerun()
            
            st.markdown("---")

# ============================================================
# LEAD DETAIL VIEW
# ============================================================
def show_lead_detail():
    if not st.session_state.selected_lead:
        st.session_state.view = "leads"
        st.rerun()
        return
    
    lead_df = get_lead_by_id(st.session_state.selected_lead)
    if lead_df is None or lead_df.empty:
        st.error("Lead not found")
        return
    
    lead = lead_df.iloc[0]
    
    # Back button
    if st.button("← Back to Leads"):
        st.session_state.view = "leads"
        st.session_state.selected_lead = None
        st.rerun()
    
    st.markdown("---")
    
    # Header
    name = f"{lead['firstName'] or ''} {lead['lastName'] or ''}".strip()
    st.markdown(f'<p class="main-header">{name}</p>', unsafe_allow_html=True)
    st.markdown(f"**{lead['jobTitle'] or 'N/A'}** at **{lead['companyName'] or 'N/A'}**")
    
    # Status and actions
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        current_status = lead['status'] or 'pending_review'
        new_status = st.selectbox(
            "Status",
            ["pending_review", "unlocked", "emailed", "responded"],
            index=["pending_review", "unlocked", "emailed", "responded"].index(current_status)
        )
        if new_status != current_status:
            if st.button("Update Status", type="primary"):
                update_lead(lead['id'], {"status": new_status})
                st.success("Status updated!")
                st.rerun()
    
    with col2:
        if lead['linkedInURL']:
            st.markdown(f"[🔗 View LinkedIn Profile]({lead['linkedInURL']})")
        if lead['websiteURL']:
            st.markdown(f"[🌐 Company Website]({lead['websiteURL']})")
    
    with col3:
        # Unlock email button
        if current_status == 'pending_review' and lead['apollo_id']:
            st.markdown("### 🔓 Unlock Email")
            if st.button("Unlock Email (1 credit)", type="primary"):
                with st.spinner("Unlocking email via Apollo..."):
                    result = unlock_email_apollo(lead['apollo_id'])
                    if result['success'] and result['email']:
                        update_lead(lead['id'], {
                            "emailAddress": result['email'],
                            "status": "unlocked",
                            "credits_used": True
                        })
                        st.success(f"Email unlocked: {result['email']}")
                        st.cache_resource.clear()
                        st.rerun()
                    else:
                        st.error(f"Failed to unlock: {result.get('error', 'No email found')}")
    
    st.markdown("---")
    
    # Lead details
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Contact Information")
        st.markdown(f"**Email:** {lead['emailAddress'] or '🔒 Locked'}")
        st.markdown(f"**Phone:** {lead['Number'] or 'N/A'}")
        st.markdown(f"**Location:** {lead['location'] or 'N/A'}")
        st.markdown(f"**Country:** {lead['country'] or 'N/A'}")
    
    with col2:
        st.markdown("### Company Information")
        st.markdown(f"**Company:** {lead['companyName'] or 'N/A'}")
        st.markdown(f"**Industry:** {lead['businessIndustry'] or 'N/A'}")
        st.markdown(f"**Seniority:** {lead['seniority'] or 'N/A'}")
    
    # AI Analysis
    if lead['ai_score'] or lead['ai_notes']:
        st.markdown("---")
        st.markdown("### 🤖 AI Analysis")
        col1, col2 = st.columns([1, 3])
        with col1:
            score = lead['ai_score'] or 0
            st.metric("AI Score", f"{score}/100")
        with col2:
            if lead['ai_notes']:
                st.markdown(lead['ai_notes'])
    
    # Email sequences
    st.markdown("---")
    st.markdown("### 📧 Email Sequences")
    
    # Check which email columns exist and display them
    email_cols = [col for col in lead.index if 'email' in col.lower() and ('body' in col.lower() or 'subject' in col.lower())]
    
    if email_cols:
        for i in range(1, 4):
            # Try different naming patterns
            subject = None
            body = None
            sent = None
            
            for col in lead.index:
                col_lower = col.lower()
                if f'email#{i}' in col_lower.replace(' ', '') or f'email {i}' in col_lower or f'email{i}' in col_lower:
                    if 'subject' in col_lower:
                        subject = lead.get(col)
                    elif 'body' in col_lower:
                        body = lead.get(col)
                if f'email {i} sent' in col_lower:
                    sent = lead.get(col)
            
            if subject or body:
                with st.expander(f"Email {i} {'✅ Sent' if sent == 'yes' else '📝 Draft'}"):
                    st.markdown(f"**Subject:** {subject or 'N/A'}")
                    st.markdown("**Body:**")
                    st.markdown(body or 'N/A')
    else:
        st.info("No email sequences found for this lead.")

# ============================================================
# SIDEBAR
# ============================================================
def show_sidebar():
    with st.sidebar:
        st.markdown("## 🎯 SKurated")
        st.markdown("B2B Pipeline Manager")
        st.markdown("---")
        
        if st.button("🏠 Dashboard", use_container_width=True):
            st.session_state.view = "dashboard"
            st.rerun()
        
        if st.button("📋 All Leads", use_container_width=True):
            st.session_state.view = "leads"
            st.rerun()
        
        st.markdown("---")
        
        # Quick stats
        stats = get_lead_stats()
        if stats is not None and not stats.empty:
            stats = stats.iloc[0]
            credits_used = int(stats['credits_used'] or 0)
            st.markdown(f"**Credits:** {MONTHLY_CREDITS - credits_used}/{MONTHLY_CREDITS}")
            st.progress((MONTHLY_CREDITS - credits_used) / MONTHLY_CREDITS)
        
        st.markdown("---")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.selected_lead = None
            st.session_state.view = "dashboard"
            st.rerun()

# ============================================================
# MAIN APP
# ============================================================
def main():
    if not st.session_state.authenticated:
        show_login()
    else:
        show_sidebar()
        
        if st.session_state.view == "dashboard":
            show_dashboard()
        elif st.session_state.view == "leads":
            show_leads()
        elif st.session_state.view == "detail":
            show_lead_detail()

if __name__ == "__main__":
    main()
    
