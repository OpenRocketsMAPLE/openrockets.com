// Initialize Supabase Data source
const supabaseUrl = 'https://ywxyoxsdrmrlokkqppoc.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl3eHlveHNkcm1ybG9ra3FwcG9jIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3MTQ1NjQsImV4cCI6MjA5MTI5MDU2NH0.s1L8ns_iV9rr4S2a15BAq6e4EwdiA2TlWWt_RdcQaKo';
const supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey);

// DOM Elements
const contentDiv = document.getElementById('content');
const msgEl = document.getElementById('message');
const pageTitle = document.getElementById('page-title');
const loginLink = document.getElementById('login-link');
const userEmailSpan = document.getElementById('user-email');
const logoutBtn = document.getElementById('logout-btn');

// Templates
const tplLogin = document.getElementById('tpl-login');
const tplSubmit = document.getElementById('tpl-submit');

// App state
let currentUser = null;
let currentUsername = null;
let currentPage = 0;
let currentOffset = 0;
let isLoading = false;
let hasMore = true;
const FEED_PAGE_SIZE = 11;
const FETCH_BATCH_SIZE = 20;
const INFINITE_SCROLL_THRESHOLD = 120;
const PAGE_BACKGROUND_IMAGE = 'https://images.wallpapersden.com/image/download/rio-de-janeiro-hd-brazil_bW5oaG2UmZqaraWkpJRnZWdqrWZlbWU.jpg';
const FALLBACK_BACKGROUND_IMAGE = 'https://upload.wikimedia.org/wikipedia/commons/thumb/e/ef/Rio_de_Janeiro%2C_Brazil_001.jpg/3840px-Rio_de_Janeiro%2C_Brazil_001.jpg';
const HIDDEN_SEEDED_STORY_TITLES = new Set([
    'welcome to the new completely static hacker news clone',
    'supabase docs: quickstart',
    'react is out, static html is back in'
]);

// ========== MODERATION (client-side) ==========
const MODERATION = {
    enabled: true,
    extraBlockedTerms: [],
    blockedTerms: [],
    blockedPatterns: [],
    ready: false
};

function normalizeForModeration(value) {
    return (value || '')
        .toString()
        .toLowerCase()
        // simple leetspeak normalization
        .replace(/[@]/g, 'a')
        .replace(/[0]/g, 'o')
        .replace(/[1!|]/g, 'i')
        .replace(/[3]/g, 'e')
        .replace(/[5$]/g, 's')
        .replace(/[7]/g, 't')
        .replace(/[\*_\.\-]/g, '')
        .replace(/[^a-z0-9\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

async function initModeration() {
    try {
        const resp = await fetch('js/moderation_terms.json', { cache: 'no-store' });
        if (resp.ok) {
            const json = await resp.json();
            const terms = Array.isArray(json.blockedTerms) ? json.blockedTerms : [];
            const regexList = Array.isArray(json.blockedRegex) ? json.blockedRegex : [];
            MODERATION.blockedTerms = terms.map(t => normalizeForModeration(t)).filter(Boolean);
            MODERATION.blockedPatterns = regexList
                .map(s => {
                    try { return new RegExp(s, 'i'); } catch { return null; }
                })
                .filter(Boolean);
        }
    } catch (e) {
        console.warn('Moderation terms failed to load', e);
    }

    if (window.leoProfanity && window.leoProfanity.loadDictionary) {
        try {
            window.leoProfanity.loadDictionary();
            if (MODERATION.extraBlockedTerms.length > 0) {
                window.leoProfanity.add(MODERATION.extraBlockedTerms);
            }
        } catch (e) {
            console.warn('leo-profanity init failed', e);
        }
    }

    MODERATION.ready = true;
}

async function loadCurrentUsername() {
    currentUsername = null;
    if (!currentUser || !currentUser.email) return;
    try {
        const { data } = await supabaseClient.from('user_profiles').select('username').eq('email', currentUser.email).maybeSingle();
        if (data && data.username) currentUsername = data.username;
    } catch (e) {
        console.warn('Failed to load profile username', e);
    }
}

function passesModeration(text) {
    if (!MODERATION.enabled) return { ok: true };
    if (!MODERATION.ready) return { ok: false, reason: 'Safety filter loading' };

    const normalized = normalizeForModeration(text);
    if (normalized) {
        const padded = ` ${normalized} `;
        for (const term of (MODERATION.blockedTerms || [])) {
            if (!term) continue;
            if (padded.includes(` ${term} `)) return { ok: false, reason: 'Blocked term' };
        }
        for (const pattern of (MODERATION.blockedPatterns || [])) {
            if (pattern.test(normalized)) return { ok: false, reason: 'Blocked pattern' };
        }
    }

    if (window.leoProfanity && window.leoProfanity.check) {
        try {
            const blocked = window.leoProfanity.check(normalized);
            if (blocked) return { ok: false, reason: 'Blocked term' };
        } catch (e) {
            console.warn('leo-profanity check failed', e);
        }
    }

    return { ok: true };
}

function contentAllowedOrNull(text) {
    const check = passesModeration(text);
    return check.ok ? true : false;
}

function randomAvatarUrl() {
    return AVATAR_URLS[Math.floor(Math.random() * AVATAR_URLS.length)];
}

function svgIcon(path, color = '#111', size = 14) {
    return `<svg class="icon-inline" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="${path}" fill="${color}"/></svg>`;
}

function tierIconSvg(tier) {
    const color = tier.color || '#111';
    const paths = {
        MICRO: 'M12 2l2.2 6.1L20 10l-5.8 1.9L12 18l-2.2-6.1L4 10l5.8-1.9L12 2z',
        MINI: 'M12 2l2.8 5.6L21 9l-4.5 4.4L17.6 21 12 18l-5.6 3 1.1-7.6L3 9l6.2-1.4L12 2z',
        PRO: 'M4 20h16v-2H4v2zm2-4h12v-2H6v2zm2-4h8V8H8v4zm1-6h6V2H9v4z',
        GUARDIAN: 'M4 20h16v-2H4v2zm2-4h12v-6H6v6zm2-8h8V4H8v4z',
        FAMOUS: 'M12 2l4 4-2 6-2 2-2-2-2-6 4-4zm0 14l2 2-2 4-2-4 2-2z',
        STAR: 'M12 3l7 7-7 11-7-11 7-7z',
        legend: 'M6 18h12l-1-8-5 5-5-5-1 8zm6-16l4 6-4 2-4-2 4-6z'
    };
    return svgIcon(paths[tier.icon] || paths.MICRO, color, 14);
}

function badgeIconSvg(type, color = '#111') {
    const paths = {
        hot_take: 'M12 2c2 3-1 4 1 7 1 2 4 2 4 6 0 4-3 7-5 7s-5-3-5-7c0-2 1-3 2-4 2-2 1-5 3-9z',
        insightful: 'M9 21h6v-2H9v2zm3-19a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z',
        bullseye: 'M12 2a10 10 0 110 20 10 10 0 010-20zm0 6a4 4 0 100 8 4 4 0 000-8z'
    };
    return svgIcon(paths[type] || paths.insightful, color, 14);
}

function gemIconSvg(color = '#3b82f6') {
    return svgIcon('M12 2l8 6-8 14-8-14 8-6z', color, 14);
}

function rankIconSvg(color = '#111') {
    return svgIcon('M4 20h16v-2H4v2zm2-4h12l-2-10H8L6 16z', color, 14);
}

function pointsIconSvg(color = '#111') {
    return svgIcon('M12 2l3 6 7 1-5 4 1 7-6-3-6 3 1-7-5-4 7-1 3-6z', color, 14);
}

function postsIconSvg(color = '#111') {
    return svgIcon('M4 4h16v4H4V4zm0 6h16v4H4v-4zm0 6h16v4H4v-4z', color, 14);
}

function getCurrentUsername() {
    return currentUsername || (currentUser ? currentUser.email.split('@')[0] : null);
}

function showBlockedModal() {
    const overlay = document.createElement('div');
    overlay.className = 'blocked-overlay';
    overlay.style = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999;';
    overlay.innerHTML = `<div style="background:#fff;padding:18px;max-width:520px;border-radius:8px;color:#111;box-shadow:0 6px 24px rgba(0,0,0,0.2);">
        <h3 style="margin-top:0;">Submission blocked</h3>
        <p>Please remove hate speech or inappropriate language. This platform is dedicated to teens sharing projects respectfully; general-purpose or adult content is not allowed.</p>
        <p style="font-size:13px;color:#555;">We may retain IP addresses and account identifiers and may suspend accounts or IPs for repeated abuse in accordance with COPPA/GDPR obligations.</p>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;"><button id="blocked-close" class="submit-btn">Close</button></div>
    </div>`;
    document.body.appendChild(overlay);
    document.getElementById('blocked-close').onclick = () => overlay.remove();
}

async function scanUrlForContent(url) {
    try {
        // Always scan URL string itself (domain/path/query)
        const urlCheck = passesModeration(url);
        if (!urlCheck.ok) return urlCheck;
        const resp = await fetch(url, { mode: 'cors' });
        if (!resp.ok) return { ok: false, reason: 'Unable to scan URL content' };
        const text = await resp.text();
        // crude strip tags
        const stripped = text.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<[^>]+>/g, ' ');
        const check = passesModeration(stripped);
        return check;
    } catch (e) {
        // CORS or network error - block to be safe
        return { ok: false, reason: 'Unable to scan URL content' };
    }
}

function formatRemainingTime(ms) {
    const totalSeconds = Math.max(1, Math.ceil(ms / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    if (minutes === 0) return `${seconds}s`;
    return `${minutes}m ${seconds}s`;
}

async function saveBio(username) {
    const input = document.getElementById('bio-input');
    if (!input) return;
    const bio = input.value.trim();
    const { error } = await supabaseClient.from('user_profiles').update({ bio }).eq('username', username);
    if (error) {
        alert(error.message || 'Failed to save bio');
        return;
    }
    showToast('Bio updated');
}

function drawTierProgress(canvasId, pct, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#e5e5e5';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, Math.max(0, Math.min(1, pct / 100)) * w, h);
}

// ========== GAMIFICATION: Tiers, Badges & Gems ==========
const TIERS = [
    { min: 0,     name: 'MICRO',       color: '#888',    icon: 'MICRO' },
    { min: 50,    name: 'MINI', color: '#3b82f6', icon: 'MINI' },
    { min: 200,   name: 'PRO',    color: '#22c55e', icon: 'PRO' },
    { min: 500,   name: 'GUARDIAN',  color: '#8b5cf6', icon: 'GUARDIAN' },
    { min: 1500,  name: 'FAMOUS',  color: '#f59e0b', icon: 'R-STAR' },
    { min: 5000,  name: 'STAR',    color: '#ef4444', icon: 'STAR' },
    { min: 15000, name: 'MAX',     color: '#ec4899', icon: 'MAX' },
];
const AVATAR_URLS = [
    'https://github.com/5673.png',
    'https://github.com/nio.png',
    'https://github.com/n3.png',
    'https://github.com/n6.png',
    'https://github.com/n7.png',
    'https://github.com/n9.png',
    'https://github.com/n10.png'
];
const GEM_AWARDS = {
    POST_STORY: 5, RECEIVE_UPVOTE_STORY: 10, RECEIVE_UPVOTE_COMMENT: 5,
    POST_COMMENT: 2, COMMENT_MILESTONE_10: 25, STORY_MILESTONE_25: 50,
    RECEIVE_DOWNVOTE: -2,
};
const COMMENT_BADGE_DEFS = {
    hot_take:   { name: 'Hot Take',   threshold: 10 },
    insightful: { name: 'Insightful', threshold: 5, minDepth: 3 },
    bullseye:   { name: 'Bullseye',   threshold: 10, firstOnly: true },
};
const TELESCOPE_FULL_DEPTH = 2;
const TELESCOPE_COLLAPSED_DEPTH = 4;
const TELESCOPE_MAX_DEPTH = 10;
const SURFACE_GEM_MIN_VOTES = 5;
const SURFACE_GEM_MIN_DEPTH = 3;

function getTierForGems(gems) {
    let tier = TIERS[0];
    for (const t of TIERS) { if (gems >= t.min) tier = t; }
    return tier;
}
function getNextTier(gems) {
    for (const t of TIERS) { if (gems < t.min) return t; }
    return null;
}
function tierBadgeHtml(tierObj, small = false) {
    if (!tierObj) tierObj = TIERS[0];
    const sz = small ? '11px' : '13px';
    return `<span class="tier-badge" style="color:${tierObj.color};font-size:${sz};" title="${tierObj.name}">${tierIconSvg(tierObj)}</span>`;
}

async function applyTierBadgesForUsers(usernames) {
    const unique = [...new Set((usernames || []).filter(Boolean))];
    if (unique.length === 0) return;
    const { data } = await supabaseClient
        .from('user_profiles')
        .select('username,gems')
        .in('username', unique);
    (data || []).forEach(row => {
        _tierCache[row.username] = getTierForGems(row.gems || 0);
    });
    unique.forEach(name => {
        const tier = getCachedTier(name);
        document.querySelectorAll(`[data-tier-badge="${name}"]`).forEach(el => {
            el.innerHTML = tierBadgeHtml(tier, true);
        });
    });
}

function canPostNow() {
    const key = 'post_rate_limit';
    const now = Date.now();
    const windowMs = 5 * 60 * 1000;
    const maxPosts = 2;
    const raw = localStorage.getItem(key);
    const timestamps = raw ? JSON.parse(raw) : [];
    const recent = timestamps.filter(ts => (now - ts) < windowMs);
    if (recent.length >= maxPosts) return { ok: false, remainingMs: windowMs - (now - recent[0]) };
    recent.push(now);
    localStorage.setItem(key, JSON.stringify(recent));
    return { ok: true };
}

// Toast notifications
function showToast(message, duration = 3000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.innerHTML = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast-show'));
    setTimeout(() => {
        toast.classList.remove('toast-show');
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

// Ensure user_profile exists (auto-create on first action)
async function ensureUserProfile(username) {
    const { data } = await supabaseClient.from('user_profiles').select('*').eq('username', username).maybeSingle();
    if (data) return data;
    const { data: created, error } = await supabaseClient.from('user_profiles').insert({
        username,
        gems: 0,
        tier: 0,
        tier_name: 'MICRO',
        contribution_points: 0,
        post_count: 0,
        avatar_url: randomAvatarUrl()
    }).select().single();
    if (error) { console.warn('Profile create error:', error); return null; }
    return created;
}

// Award gems and update tier
async function awardGems(username, amount, reason, refType = null, refId = null) {
    if (!username || amount === 0) return;
    try {
        await supabaseClient.from('gem_transactions').insert({ username, amount, reason, reference_type: refType, reference_id: refId });
        const profile = await ensureUserProfile(username);
        if (profile) {
            const newGems = Math.max(0, (profile.gems || 0) + amount);
            const newTier = getTierForGems(newGems);
            const tierIndex = TIERS.indexOf(newTier);
            await supabaseClient.from('user_profiles').update({ gems: newGems, tier: tierIndex, tier_name: newTier.name }).eq('username', username);
            if (tierIndex > (profile.tier || 0)) {
                showToast(`<b>Tier Up!</b> You're now a <span style="color:${newTier.color}">${newTier.name}</span>!`, 5000);
            }
        }
        if (amount > 0) showToast(`<b>+${amount} gems</b> ${reason}`);
    } catch (e) { console.warn('Gem award error:', e); }
}

// Fetch user tier for display
const _tierCache = {};
async function getUserTier(username) {
    if (_tierCache[username]) return _tierCache[username];
    const { data } = await supabaseClient.from('user_profiles').select('gems,tier,tier_name').eq('username', username).maybeSingle();
    const tier = data ? getTierForGems(data.gems || 0) : TIERS[0];
    _tierCache[username] = tier;
    return tier;
}
function getCachedTier(username) {
    return _tierCache[username] || TIERS[0];
}

function loadingMarkup(label = 'Getting things ready..') {
    return `
        <div class="loading-wrap" aria-live="polite">
            <p class="info">${label}</p>
        </div>
    `;
}

function setLogoLoading(loading) {
    document.body.classList.toggle('is-loading', loading);
}

function preloadPageBackground() {
    const img = new Image();
    img.onload = () => document.body.classList.add('bg-ready');
    img.onerror = () => {
        document.body.style.setProperty('--rio-background', `url('${FALLBACK_BACKGROUND_IMAGE}')`);
        const fallbackImg = new Image();
        fallbackImg.onload = () => document.body.classList.add('bg-ready');
        fallbackImg.onerror = () => document.body.classList.add('bg-ready');
        fallbackImg.src = FALLBACK_BACKGROUND_IMAGE;
    };
    img.src = PAGE_BACKGROUND_IMAGE;
}

function normalizeText(value) {
    return (value || '').trim().toLowerCase();
}

function getAuthorName(record) {
    if (!record) return 'Anonymous';
    return record.by || record.author || record.username || record.user_id || 'Anonymous';
}

function isVisibleStory(story) {
    return story && !HIDDEN_SEEDED_STORY_TITLES.has(normalizeText(story.title));
}

function getNetVotes(item) {
    if (item && (item.upvotes !== undefined || item.downvotes !== undefined)) {
        return (item.upvotes || 0) - (item.downvotes || 0);
    }
    return item && item.score ? item.score : 0;
}

async function fetchStories(view, offset, limit) {
    const buildBase = () => supabaseClient
        .from('stories')
        .select('*', { count: 'exact' });

    if (view === 'newest') {
        let response = await buildBase()
            .order('last_activity_at', { ascending: false })
            .range(offset, offset + limit - 1);
        if (response.error && /last_activity_at|column/i.test(response.error.message || '')) {
            response = await buildBase()
                .order('created_at', { ascending: false })
                .range(offset, offset + limit - 1);
        }
        return response;
    }

    return buildBase()
        .order('score', { ascending: false })
        .order('created_at', { ascending: false })
        .range(offset, offset + limit - 1);
}

function showMessage(msg) { msgEl.textContent = msg; msgEl.style.display = 'block'; }
function hideMessage() { msgEl.style.display = 'none'; }

function checkAuth() {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
        currentUser = session ? session.user : null;
        updateNavAuth();
        loadCurrentUsername();
    });
    supabaseClient.auth.onAuthStateChange((_event, session) => {
        currentUser = session ? session.user : null;
        updateNavAuth();
        loadCurrentUsername();
    });
}

function updateNavAuth() {
    if (currentUser) {
        loginLink.style.display = 'none';
        userEmailSpan.style.display = 'inline-block';
        userEmailSpan.textContent = getCurrentUsername() || currentUser.email;
        logoutBtn.style.display = 'inline-block';
    } else {
        loginLink.style.display = 'inline-block';
        userEmailSpan.style.display = 'none';
        logoutBtn.style.display = 'none';
    }
}

async function handleLogout() {
    await supabaseClient.auth.signOut();
    navigate('top');
}

function navigate(view) {
    const url = new URL(window.location);
    url.search = '';
    if (view === 'newest') url.searchParams.set('v', 'newest');
    else if (view === 'login') url.searchParams.set('v', 'login');
    else if (view === 'submit') url.searchParams.set('v', 'submit');
    try {
        window.history.pushState({}, '', url);
    } catch(e) {
        window.location.search = url.search;
    }
    handleRoute();
}

function navigatePost(id) {
    const url = new URL(window.location);
    url.search = '';
    url.searchParams.set('id', id);
    try {
        window.history.pushState({}, '', url);
    } catch(e) {
        window.location.search = url.search;
    }
    handleRoute();
}

function navigateProfile(username) {
    const url = new URL(window.location);
    url.search = '';
    url.searchParams.set('profile', username);
    try {
        window.history.pushState({}, '', url);
    } catch(e) {
        window.location.search = url.search;
    }
    handleRoute();
}

function timeAgo(time) {
    const timeInSec = new Date(time).getTime() / 1000;
    const currentTime = Math.floor(Date.now() / 1000);
    const minutes = Math.floor((currentTime - timeInSec) / 60);
    if (minutes < 60) return `${minutes} minutes ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hours ago`;
    return `${Math.floor(hours / 24)} days ago`;
}

function getDomainFromUrl(url) {
    if (!url) return '';
    try {
        return new URL(url).hostname.replace('www.', '');
    } catch { return ''; }
}

function getVoterId() {
    return currentUser && currentUser.id;
}

function setVoteButtonState(targetId, targetType, currentValue) {
    const upButtons = document.querySelectorAll(`[data-vote-btn="${targetType}-${targetId}-1"]`);
    const downButtons = document.querySelectorAll(`[data-vote-btn="${targetType}-${targetId}--1"]`);
    upButtons.forEach(btn => btn.classList.toggle('voted-up', currentValue === 1));
    downButtons.forEach(btn => btn.classList.toggle('voted-down', currentValue === -1));
}

async function applyUserVoteStates({ storyIds = [], commentIds = [] }) {
    if (!currentUser) return;
    const voterId = getVoterId();
    if (!voterId) return;

    storyIds.forEach(id => setVoteButtonState(id, 'story', 0));
    commentIds.forEach(id => setVoteButtonState(id, 'comment', 0));

    if (storyIds.length > 0) {
        const { data: storyVotes } = await supabaseClient
            .from('votes')
            .select('target_id,value,target_type')
            .eq('voter', voterId)
            .eq('target_type', 'story')
            .in('target_id', storyIds);
        (storyVotes || []).forEach(v => setVoteButtonState(v.target_id, 'story', v.value));
    }

    if (commentIds.length > 0) {
        const { data: commentVotes } = await supabaseClient
            .from('votes')
            .select('target_id,value,target_type')
            .eq('voter', voterId)
            .eq('target_type', 'comment')
            .in('target_id', commentIds);
        (commentVotes || []).forEach(v => setVoteButtonState(v.target_id, 'comment', v.value));
    }
}

async function vote(targetId, targetType, voteValue) {
    if (!currentUser) { navigate('login'); return; }
    let previousVote = 0;
    try {
        const voterId = getVoterId();
        if (!voterId) throw new Error('Unable to identify the signed-in user.');
        const { data: existing } = await supabaseClient
            .from('votes')
            .select('*')
            .eq('voter', voterId)
            .eq('target_id', targetId)
            .eq('target_type', targetType)
            .maybeSingle();

        let table = targetType === 'story' ? 'stories' : 'comments';
        const oldVote = existing ? existing.value : 0;
        previousVote = oldVote;
        let newVote = voteValue;
        if (existing) {
            if (existing.value === voteValue) {
                const { error: deleteError } = await supabaseClient.from('votes').delete().eq('id', existing.id);
                if (deleteError) throw deleteError;
                newVote = 0;
            } else {
                const { error: updateVoteError } = await supabaseClient.from('votes').update({ value: voteValue }).eq('id', existing.id);
                if (updateVoteError) throw updateVoteError;
            }
        } else {
            const { error: insertVoteError } = await supabaseClient.from('votes').insert({
                voter: voterId,
                target_id: targetId,
                target_type: targetType,
                value: voteValue
            });
            if (insertVoteError) throw insertVoteError;
        }

        // Immediate UI feedback
        setVoteButtonState(targetId, targetType, newVote);
        const delta = newVote - oldVote;
        const countEl = document.getElementById(targetType === 'story' ? `votes-${targetId}` : `comment-votes-${targetId}`);
        const scoreEl = document.getElementById(`score-${targetId}`);
        if (countEl) {
            const current = parseInt(countEl.textContent, 10) || 0;
            countEl.textContent = current + delta;
        }
        if (scoreEl) {
            const current = parseInt(scoreEl.textContent, 10) || 0;
            scoreEl.textContent = current + delta;
        }

        const { data: obj, error: targetError } = await supabaseClient.from(table).select('upvotes,downvotes,score').eq('id', targetId).single();
        if (targetError) throw targetError;
        if (obj) {
            const nextUpvotes = Math.max(0, (obj.upvotes || 0) + (newVote === 1 ? 1 : 0) - (oldVote === 1 ? 1 : 0));
            const nextDownvotes = Math.max(0, (obj.downvotes || 0) + (newVote === -1 ? 1 : 0) - (oldVote === -1 ? 1 : 0));
            const { error: scoreError } = await supabaseClient.from(table).update({
                upvotes: nextUpvotes,
                downvotes: nextDownvotes,
                score: nextUpvotes - nextDownvotes
            }).eq('id', targetId);
            if (scoreError) throw scoreError;
        }
        
        const { data: updatedObj } = await supabaseClient.from(table).select('*').eq('id', targetId).single();
        if (updatedObj) {
            const netVotes = getNetVotes(updatedObj);
            const voteEl1 = document.getElementById(`votes-${targetId}`);
            if (voteEl1) voteEl1.textContent = netVotes;
            const voteEl2 = document.getElementById(`score-${targetId}`);
            if (voteEl2) voteEl2.textContent = netVotes;
            const voteEl3 = document.getElementById(`comment-votes-${targetId}`);
            if (voteEl3) voteEl3.textContent = netVotes;

            // Award gems to the content author
            const targetAuthor = getAuthorName(updatedObj);
            if (targetAuthor && targetAuthor !== getCurrentUsername()) {
                if (newVote === 1 && oldVote !== 1) {
                    const gemAmount = targetType === 'story' ? GEM_AWARDS.RECEIVE_UPVOTE_STORY : GEM_AWARDS.RECEIVE_UPVOTE_COMMENT;
                    awardGems(targetAuthor, gemAmount, `Received upvote on ${targetType}`, targetType, targetId);
                } else if (newVote === -1 && oldVote !== -1) {
                    awardGems(targetAuthor, GEM_AWARDS.RECEIVE_DOWNVOTE, `Received downvote on ${targetType}`, targetType, targetId);
                }
            }
        }
        // Vote button animation
        const btnClass = voteValue === 1 ? `vote-up-${targetId}` : `vote-down-${targetId}`;
        document.querySelectorAll(`[data-vote-anim="${targetId}-${voteValue}"]`).forEach(btn => {
            btn.classList.add('vote-pulse');
            setTimeout(() => btn.classList.remove('vote-pulse'), 300);
        });
    } catch (err) {
        console.error('Vote error:', err);
        // revert UI on error
        setVoteButtonState(targetId, targetType, previousVote);
        alert(err.message || 'Failed to vote');
    }
}

async function handleRoute() {
    hideMessage();
    window.onscroll = null;
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    const profile = params.get('profile');
    const view = params.get('v') || 'top';
    contentDiv.innerHTML = '';
    currentPage = 0;
    currentOffset = 0;
    hasMore = true;
    if (id) {
        await loadSinglePost(id);
    } else if (profile) {
        await loadProfile(profile);
    } else if (view === 'login') {
        renderLoginView();
    } else if (view === 'submit') {
        renderSubmitView();
    } else {
        await loadFeed(view);
    }
}

async function loadFeed(view) {
    pageTitle.textContent = view === 'newest' ? 'Latest' : 'Popular';
    if (currentPage === 0) {
        contentDiv.innerHTML = loadingMarkup();
    }
    if (isLoading || !hasMore) return;
    isLoading = true;
    setLogoLoading(true);
    try {
        const visibleStories = [];
        while (visibleStories.length < FEED_PAGE_SIZE && hasMore) {
            const { data: stories, error, count } = await fetchStories(view, currentOffset, FETCH_BATCH_SIZE);
            if (error) throw error;
            if (!stories || stories.length === 0) {
                hasMore = false;
                break;
            }
            currentOffset += stories.length;
            visibleStories.push(...stories.filter(isVisibleStory));
            if (currentOffset >= count) hasMore = false;
        }
        const storiesToRender = visibleStories.filter(s => contentAllowedOrNull(`${s.title || ''} ${s.url || ''} ${s.content || ''}`));
        if (storiesToRender.length === 0) {
            if (currentPage === 0) {
                contentDiv.innerHTML = '<p class="info" style="text-align:center;">No stories found.</p>';
            }
            return;
        }
        await renderFeedIncremental(storiesToRender);
        await applyUserVoteStates({ storyIds: storiesToRender.map(s => s.id) });
        await applyTierBadgesForUsers(storiesToRender.map(s => getAuthorName(s)));
        currentPage++;
        window.onscroll = async () => {
            const scrollableDistance = document.documentElement.scrollHeight - window.innerHeight;
            if (scrollableDistance > window.innerHeight && (window.innerHeight + window.scrollY) >= document.documentElement.scrollHeight - INFINITE_SCROLL_THRESHOLD && hasMore && !isLoading) {
                await loadFeed(view);
            }
        };
    } catch (err) {
        console.error(err);
        showMessage('Unable to load stories.');
        if (currentPage === 0) {
            contentDiv.innerHTML = '<p class="info" style="text-align:center; color: red;">Unable to load stories.</p>';
        }
    } finally {
        isLoading = false;
        setLogoLoading(false);
    }
}

function buildStoryHtml(story) {
    const domain = getDomainFromUrl(story.url);
    const titleAttrs = story.url
        ? `href="${story.url}" target="_blank" rel="noopener noreferrer"`
        : `href="javascript:void(0);" onclick="navigatePost(${story.id})"`;
    const netVotes = getNetVotes(story);
    const authorName = getAuthorName(story);
    return `
        <div class="story" style="padding: 12px 0; border-bottom: 1px solid #e5e5e5;">
            <div class="enum" style="display: flex; flex-direction: column; gap: 4px; align-items: center; margin-right: 10px;">
                <button data-vote-btn="story-${story.id}-1" onclick="vote(${story.id}, 'story', 1)" style="background: none; border: none; cursor: pointer; font-size: 16px; padding: 0;">▲</button>
                <span id="votes-${story.id}" style="min-width: 30px; text-align: center;">${netVotes}</span>
                <button data-vote-btn="story-${story.id}--1" onclick="vote(${story.id}, 'story', -1)" style="background: none; border: none; cursor: pointer; font-size: 16px; padding: 0;">▼</button>
            </div>
            <div class="story-content">
                <div class="title">
                    <a ${titleAttrs} style="font-weight: 500; color: #000; text-decoration: none;">${story.title}</a>
                    ${domain ? `<span style="font-size: 12px; color: #000; margin-left: 8px;">(${domain})</span>` : ''}
                </div>
                <p class="info" style="font-size: 12px; color: #000; margin: 6px 0;">
                    <a href="javascript:void(0);" onclick="navigateProfile('${authorName}')" style=" color: #111111; text-decoration: none;">By <b>${authorName}</b>  <span data-tier-badge="${authorName}"></span>,</a>
                    ${timeAgo(story.created_at)} |
                    <button class="submit-btn" style="padding: 2px 6px; font-size: 10px; margin-left: 5px;" onclick="navigatePost(${story.id})">discuss</button>
                </p>
            </div>
        </div>`;
}

async function renderFeedIncremental(stories) {
    if (currentPage === 0) contentDiv.innerHTML = '';
    for (const story of stories) {
        // small yield so UI updates between inserts
        // eslint-disable-next-line no-await-in-loop
        await new Promise(r => setTimeout(r, 0));
        contentDiv.insertAdjacentHTML('beforeend', buildStoryHtml(story));
    }
}

function renderLoginView() {
    pageTitle.textContent = '';
    contentDiv.appendChild(tplLogin.content.cloneNode(true));
    const forgotLink = document.getElementById('forgot-link');
    if (forgotLink) {
        forgotLink.onclick = (e) => {
            e.preventDefault();
            const overlay = document.createElement('div');
            overlay.className = 'forgot-overlay';
            overlay.style = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999;';
            overlay.innerHTML = `<div style="background:#fff;padding:18px;max-width:520px;border-radius:8px;color:#111;box-shadow:0 6px 24px rgba(0,0,0,0.2);">
                <h3 style="margin-top:0;">Forgot password</h3>
                <p style="font-size:13px;color:#555;">For account recovery, email the team at <strong>support@openrockets.com</strong> with the email you used to sign up and a brief description. For safety reasons we do not provide automated password resets here.</p>
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;"><button id="forgot-close" class="submit-btn">Close</button></div>
            </div>`;
            document.body.appendChild(overlay);
            document.getElementById('forgot-close').onclick = () => overlay.remove();
        };
    }
    document.getElementById('login-form').onsubmit = async (e) => {
        e.preventDefault();
        const errEl = document.getElementById('auth-error');
        const msgEl = document.getElementById('auth-msg');
        errEl.style.display='none'; msgEl.style.display='none';
        const { error } = await supabaseClient.auth.signInWithPassword({
            email: e.target['login-email'].value,
            password: e.target['login-password'].value,
        });
        if (error) { errEl.textContent = error.message; errEl.style.display='block'; }
        else navigate('top');
    };
    document.getElementById('signup-form').onsubmit = async (e) => {
        e.preventDefault();
        const errEl = document.getElementById('auth-error');
        const msgEl = document.getElementById('auth-msg');
        errEl.style.display='none'; msgEl.style.display='none';
        const username = document.getElementById('signup-username').value.trim();
        const email = e.target['signup-email'].value;
        const password = e.target['signup-password'].value;

        // ensure username unique
        const { data: existing } = await supabaseClient.from('user_profiles').select('username').eq('username', username).limit(1);
        if (existing && existing.length > 0) { errEl.textContent = 'Username already taken.'; errEl.style.display='block'; return; }

        const { error, data } = await supabaseClient.auth.signUp({ email, password });
        if (error) { errEl.textContent = error.message; errEl.style.display='block'; return; }

        // create profile
        try {
            await supabaseClient.from('user_profiles').insert([{ username, email, gems: 0 }]);
        } catch (e) { console.warn('Failed to create profile', e); }
        navigate('top');
    };
}

function renderSubmitView() {
    if (!currentUser) { navigate('login'); return; }
    pageTitle.textContent = '';
    contentDiv.appendChild(tplSubmit.content.cloneNode(true));
    document.getElementById('submit-form').onsubmit = async (e) => {
        e.preventDefault();
        const errEl = document.getElementById('submit-error');
        errEl.textContent = '';
        const title = document.getElementById('post-title').value;
        const url = document.getElementById('post-url').value;
        const text = document.getElementById('post-text').value;
        if (!url && !text) {
            errEl.textContent = 'Please provide either a URL or Text.';
            return;
        }
        const rate = canPostNow();
        if (!rate.ok) {
            errEl.textContent = `Please wait ${formatRemainingTime(rate.remainingMs)} before posting again.`;
            return;
        }
        // Check content and URL
        const moderationCheck = passesModeration(`${title} ${url} ${text}`);
        if (!moderationCheck.ok) {
            // clear inputs and show modal
            document.getElementById('post-title').value = '';
            document.getElementById('post-url').value = '';
            document.getElementById('post-text').value = '';
            showBlockedModal();
            return;
        }
        if (url) {
            const urlCheck = await scanUrlForContent(url);
            if (!urlCheck.ok) {
                document.getElementById('post-title').value = '';
                document.getElementById('post-url').value = '';
                document.getElementById('post-text').value = '';
                showBlockedModal();
                return;
            }
        }
        const { error } = await supabaseClient.from('stories').insert([{
            title: title,
            url: url || null,
            content: text || null,
            by: getCurrentUsername(), 
            upvotes: 1,
            downvotes: 0
        }]);
        if (error) {
            errEl.textContent = error.message;
        } else {
            const username = getCurrentUsername();
            awardGems(username, GEM_AWARDS.POST_STORY, 'Posted a story', 'story', null);
            navigate('top');
        }
    };
}

async function loadSinglePost(id) {
    pageTitle.textContent = '';
    contentDiv.innerHTML = loadingMarkup();
    setLogoLoading(true);
    try {
        const { data: story, error } = await supabaseClient.from('stories').select('*').eq('id', id).single();
        if (error) throw error;
        const { data: commentsRaw } = await supabaseClient.from('comments').select('*').eq('story_id', id).order('created_at', { ascending: true });
        const comments = (commentsRaw || []).filter(c => contentAllowedOrNull(`${c.content || ''}`));
        const domain = getDomainFromUrl(story.url);
        const authorName = getAuthorName(story);
        const titleAttrs = story.url
            ? `href="${story.url}" target="_blank" rel="noopener noreferrer"`
            : `href="javascript:void(0);" onclick="navigatePost(${story.id})"`;
        const netVotes = getNetVotes(story);
        let commentsHtml = renderComments(comments || [], id);
        const replyFormHtml = currentUser ? `
            <div class="reply-panel" style="margin-top: 20px; padding: 15px;">
                <textarea id="comment-text" rows="4" style="width: 100%; max-width: 500px; padding: 10px; font-family: inherit; font-size: 13px; box-sizing: border-box;" placeholder="Add a comment..."></textarea><br/>
                <button onclick="submitComment(${story.id})" class="submit-btn" style="margin-top: 10px;">post comment</button>
            </div>
        ` : `<p style="color: #000; font-size: 12px; margin-top: 20px;"><a href="javascript:void(0);" onclick="navigate('login')">Login</a> to comment.</p>`;
        contentDiv.innerHTML = `
        <div class="surface-panel" style="padding:20px; border-bottom: 1px solid rgba(0,0,0,0.12);">
            <div style="display:flex; gap: 8px;">
                <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                    <button data-vote-btn="story-${story.id}-1" onclick="vote(${story.id}, 'story', 1)" style="background: none; border: none; cursor: pointer; font-size: 16px; padding: 0;">▲</button>
                    <span id="score-${story.id}" style="min-width: 30px; text-align: center;">${netVotes}</span>
                    <button data-vote-btn="story-${story.id}--1" onclick="vote(${story.id}, 'story', -1)" style="background: none; border: none; cursor: pointer; font-size: 16px; padding: 0;">▼</button>
                </div>
                <div>
                    <h3 style="margin:0 0 8px 0;"><a ${titleAttrs} style="color:#000; text-decoration:none;">${story.title}</a> ${domain ? `<span style="font-size:12px; color:#000;">(${domain})</span>` : ''}</h3>
                    <p style="font-size:12px; color:#000; margin: 5px 0;">
                        <span data-tier-badge="${authorName}"></span>
                        <a href="javascript:void(0);" onclick="navigateProfile('${authorName}')" style="color: #111; text-decoration: none;">${authorName}</a>
                        ${timeAgo(story.created_at)}
                    </p>
                    ${story.content ? `<div style="margin-top:15px; font-size:14px; line-height:1.5;">${story.content}</div>` : ''}
                    ${replyFormHtml}
                    <div style="margin-top: 30px;" id="comments-container">
                        ${commentsHtml}
                    </div>
                </div>
            </div>
        </div>
        <div style="margin-top:20px; margin-bottom: 40px; margin-left: 25px;">
            <a href="javascript:void(0);" onclick="navigate('top')" style="font-size: 13px; color: #111; text-decoration: underline;">Back</a>
        </div>
        `;
        await applyUserVoteStates({ storyIds: [story.id], commentIds: (comments || []).map(c => c.id) });
        await applyTierBadgesForUsers([authorName, ...(comments || []).map(c => getAuthorName(c))]);
    } catch (err) {
        console.error(err);
        contentDiv.innerHTML = '<p class="info" style="text-align:center; color: red;">Hmm.. post was deleted.</p>';
    } finally {
        setLogoLoading(false);
    }
}

function renderComments(comments, storyId, parentId = null, depth = 0) {
    const filtered = comments.filter(c => (c.parent_comment_id || null) === parentId);
    if (filtered.length === 0) return parentId ? '' : '<p style="font-size:13px; color:#000; margin-top: 10px;">No comments yet.</p>';
    
    // At depth 0, find surfaced Elo (highly-upvoted deep replies)
    let surfacedEloHtml = '';
    if (depth === 0) {
        surfacedEloHtml = renderSurfacedElo(comments, storyId);
    }
    
    let html = surfacedEloHtml;
    const depthColors = ['#ff6600', '#3b82f6', '#22c55e', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'];
    const borderColor = depthColors[Math.min(depth, depthColors.length - 1)];
    
    filtered.forEach(c => {
        const netVotes = getNetVotes(c);
        const marginLeft = Math.min(depth, 6) * 18;
        const authorName = getAuthorName(c);
        const tier = getCachedTier(authorName);
        const tierHtml = `<span data-tier-badge="${authorName}">${tierBadgeHtml(tier, true)}</span>`;
        
        // Comment badges
        let badgesHtml = '';
        if (netVotes >= 10) badgesHtml += `<span class="comment-badge-inline" title="Hot Take">${badgeIconSvg('hot_take', '#ef4444')}</span>`;
        if (netVotes >= 5 && depth >= 3) badgesHtml += `<span class="comment-badge-inline" title="Insightful">${badgeIconSvg('insightful', '#3b82f6')}</span>`;
        
        // Telescope depth rules
        if (depth >= TELESCOPE_MAX_DEPTH) {
            html += `
            <div class="comment-node" style="margin-left: ${marginLeft}px; border-left-color: ${borderColor};">
                <p style="font-size:12px; color:#000; font-style:italic; margin: 8px 0;">
                    <a href="javascript:void(0);" onclick="openThreadFocus(${storyId}, ${c.id})" style="color:#3b82f6;">Continue this thread </a>
                </p>
            </div>`;
            return;
        }
        
        const childComments = renderComments(comments, storyId, c.id, depth + 1);
        const childCount = countDescendants(comments, c.id);
        
        // Determine visibility
        let wrapperClass = 'comment-node';
        let collapseBtn = '';
        let childWrapper = childComments;
        
        if (depth >= TELESCOPE_COLLAPSED_DEPTH && depth < TELESCOPE_MAX_DEPTH && childCount > 0) {
            // Depth 5+: show "Dive deeper" button
            childWrapper = `
                <div class="telescope-dive">
                    <button class="submit-btn telescope-btn" onclick="openThreadFocus(${storyId}, ${c.id})">
                        ${childCount} more replies
                    </button>
                </div>`;
        } else if (depth >= TELESCOPE_FULL_DEPTH && depth < TELESCOPE_COLLAPSED_DEPTH && childCount > 0) {
            // Depth 3-4: collapsed by default
            collapseBtn = `<button class="collapse-toggle" onclick="toggleCollapse(this)" data-count="${childCount}">▸ Show ${childCount} replies</button>`;
            childWrapper = `<div class="comment-collapsed-children" style="display:none;">${childComments}</div>`;
        }
        
        html += `
        <div class="${wrapperClass}" style="margin-left: ${marginLeft}px; border-left-color:transparent;">
            <div class="comment-vote-row">
                <button data-vote-btn="comment-${c.id}-1" data-vote-anim="${c.id}-1" onclick="vote(${c.id}, 'comment', 1)" class="vote-arrow">▲</button>
                <span id="comment-votes-${c.id}" class="vote-count">${netVotes}</span>
                <button data-vote-btn="comment-${c.id}--1" data-vote-anim="${c.id}--1" onclick="vote(${c.id}, 'comment', -1)" class="vote-arrow">▼</button>
                ${badgesHtml}
            </div>
            <p class="comment-meta">
                ${tierHtml} <a href="javascript:void(0);" onclick="navigateProfile('${authorName}')" class="comment-author">${authorName}</a>
                <span class="comment-time">${timeAgo(c.created_at)}</span>
            </p>
            <div class="comment-body">${c.content}</div>
            ${currentUser ? `<button class="submit-btn tiny" onclick="showReplyForm(${c.id})">reply</button>` : ''}
            <div id="reply-form-${c.id}" class="reply-panel" style="display: none; margin-top: 10px; padding: 10px;">
                <textarea id="reply-text-${c.id}" rows="3" class="comment-textarea" placeholder="Reply..."></textarea><br/>
                <button onclick="submitReply(${storyId}, ${c.id})" class="submit-btn" style="margin-top: 8px; padding: 4px 10px; font-size: 11px;">post</button>
            </div>
            ${collapseBtn}
            ${childWrapper}
        </div>`;
    });
    return html;
}

function countDescendants(comments, parentId) {
    let count = 0;
    const children = comments.filter(c => (c.parent_comment_id || null) === parentId);
    for (const child of children) {
        count += 1 + countDescendants(comments, child.id);
    }
    return count;
}

function renderSurfacedElo(comments, storyId) {
    const Elo = [];
    function findElo(list, parentId, depth) {
        const children = list.filter(c => (c.parent_comment_id || null) === parentId);
        for (const c of children) {
            const netVotes = getNetVotes(c);
            if (depth >= SURFACE_GEM_MIN_DEPTH && netVotes >= SURFACE_GEM_MIN_VOTES) {
                Elo.push({ comment: c, depth, netVotes });
            }
            findElo(list, c.id, depth + 1);
        }
    }
    findElo(comments, null, 0);
    if (Elo.length === 0) return '';
    Elo.sort((a, b) => b.netVotes - a.netVotes);
    const top = Elo.slice(0, 3);
    let html = '<div class="surfaced-Elo-container">';
    html += '<p class="surfaced-Elo-title">Surfaced Elo — Highly upvoted replies from deep in the thread:</p>';
    for (const g of top) {
        const gemAuthor = getAuthorName(g.comment);
        const tier = getCachedTier(gemAuthor);
        html += `
        <div class="surfaced-gem-card" onclick="openThreadFocus(${storyId}, ${g.comment.id})">
            <div class="gem-card-header">
                <span>${badgeIconSvg('insightful', '#3b82f6')}</span>
                <span data-tier-badge="${gemAuthor}">${tierBadgeHtml(tier, true)}</span>
                <strong>${gemAuthor}</strong>
                <span class="gem-card-votes">▲ ${g.netVotes}</span>
                <span class="gem-card-depth">depth ${g.depth}</span>
            </div>
            <p class="gem-card-preview">${g.comment.content.substring(0, 120)}${g.comment.content.length > 120 ? '...' : ''}</p>
        </div>`;
    }
    html += '</div>';
    return html;
}

function toggleCollapse(btn) {
    const collapsed = btn.nextElementSibling;
    if (!collapsed) return;
    const isHidden = collapsed.style.display === 'none';
    collapsed.style.display = isHidden ? 'block' : 'none';
    const count = btn.getAttribute('data-count');
    btn.textContent = isHidden ? `▾ Hide ${count} replies` : `▸ Show ${count} replies`;
}

function openThreadFocus(storyId, commentId) {
    // Build a focused thread modal showing the sub-conversation
    const overlay = document.createElement('div');
    overlay.className = 'thread-focus-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    
    const modal = document.createElement('div');
    modal.className = 'thread-focus-modal';
    modal.innerHTML = '<div class="loading-wrap"><p class="info">Loading thread...</p></div>';
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('thread-focus-open'));
    
    // Fetch the sub-thread
    supabaseClient.from('comments').select('*').eq('story_id', storyId).order('created_at', { ascending: true }).then(({ data: comments }) => {
        if (!comments) { modal.innerHTML = '<p>Error loading thread.</p>'; return; }
        // Find the root comment for this sub-thread
        const root = comments.find(c => c.id === commentId);
        if (!root) { modal.innerHTML = '<p>Comment not found.</p>'; return; }
        
        // Build a flat ancestor chain
        let ancestorChain = [];
        let current = root;
        while (current) {
            ancestorChain.unshift(current);
            current = comments.find(c => c.id === (current.parent_comment_id || null));
        }
        
        let html = `<div class="thread-focus-header">
            <h3>Thread Focus</h3>
            <button class="submit-btn" onclick="this.closest('.thread-focus-overlay').remove()">✕ Close</button>
        </div>`;
        
        // Show ancestor trail
        if (ancestorChain.length > 1) {
            html += '<div class="thread-ancestors">';
            for (let i = 0; i < ancestorChain.length - 1; i++) {
                const a = ancestorChain[i];
                const ancestorName = getAuthorName(a);
                html += `<div class="thread-ancestor-item"><span data-tier-badge="${ancestorName}"></span> <strong>${ancestorName}</strong>: ${a.content.substring(0, 80)}...</div>`;
            }
            html += '</div>';
        }
        
        // Render the focused sub-tree with reset depth
        html += '<div class="thread-focus-body">' + renderComments(comments, storyId, root.parent_comment_id, 0) + '</div>';
        modal.innerHTML = html;
        applyUserVoteStates({ commentIds: (comments || []).map(c => c.id) });
        applyTierBadgesForUsers((comments || []).map(c => getAuthorName(c)));
    });
}

function showReplyForm(commentId) {
    const form = document.getElementById(`reply-form-${commentId}`);
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function submitComment(storyId) {
    if (!currentUser) { navigate('login'); return; }
    const content = document.getElementById('comment-text').value;
    if (!content.trim()) { alert('Comment cannot be empty'); return; }
    const moderationCheck = passesModeration(content);
    if (!moderationCheck.ok) { document.getElementById('comment-text').value = ''; showBlockedModal(); return; }
    try {
        const { error } = await supabaseClient.from('comments').insert({
            story_id: storyId,
            by: getCurrentUsername(),
            content: content,
            parent_comment_id: null,
            upvotes: 0,
            downvotes: 0
        });
        if (error) throw error;
        const username = getCurrentUsername();
        awardGems(username, GEM_AWARDS.POST_COMMENT, 'Posted a comment', 'comment', storyId);
        document.getElementById('comment-text').value = '';
        await updateCommentsUI(storyId);
    } catch (err) {
        console.error(err);
        alert(err.message || 'Failed to post comment');
    }
}

async function submitReply(storyId, parentCommentId) {
    if (!currentUser) { navigate('login'); return; }
    const content = document.getElementById(`reply-text-${parentCommentId}`).value;
    if (!content.trim()) { alert('Reply cannot be empty'); return; }
    const moderationCheck = passesModeration(content);
    if (!moderationCheck.ok) { document.getElementById(`reply-text-${parentCommentId}`).value = ''; showBlockedModal(); return; }
    try {
        const { error } = await supabaseClient.from('comments').insert({
            story_id: storyId,
            by: getCurrentUsername(),
            content: content,
            parent_comment_id: parentCommentId,
            upvotes: 0,
            downvotes: 0
        });
        if (error) throw error;
        const username = getCurrentUsername();
        awardGems(username, GEM_AWARDS.POST_COMMENT, 'Posted a reply', 'comment', storyId);
        document.getElementById(`reply-text-${parentCommentId}`).value = '';
        await updateCommentsUI(storyId);
    } catch (err) {
        console.error(err);
        alert(err.message || 'Failed to post reply');
    }
}

async function updateCommentsUI(storyId) {
    const { data: commentsRaw, error } = await supabaseClient.from('comments').select('*').eq('story_id', storyId).order('created_at', { ascending: true });
    if (error) throw error;
    const comments = (commentsRaw || []).filter(c => contentAllowedOrNull(`${c.content || ''}`));
    const commentsContainer = document.getElementById('comments-container');
    if (commentsContainer) {
        commentsContainer.innerHTML = renderComments(comments || [], storyId);
    }
    await applyUserVoteStates({ commentIds: (comments || []).map(c => c.id) });
    await applyTierBadgesForUsers((comments || []).map(c => getAuthorName(c)));
}

async function loadProfile(username) {
    pageTitle.textContent = `Community profile of ${username}`;
    contentDiv.innerHTML = loadingMarkup();
    setLogoLoading(true);
    try {
        const { data: profile } = await supabaseClient.from('user_profiles').select('*').eq('username', username).maybeSingle();
        const { data: posts } = await supabaseClient.from('stories').select('*').eq('by', username).order('created_at', { ascending: false });
        const { data: badges } = await supabaseClient.from('user_badges').select('*').eq('username', username).order('earned_at', { ascending: false }).limit(20);
        if (!profile && (!posts || posts.length === 0)) {
            contentDiv.innerHTML = '<p class="info" style="text-align:center;">User not found.</p>';
            return;
        }
        const gems = profile ? (profile.gems || 0) : 0;
        const tier = getTierForGems(gems);
        const nextTier = getNextTier(gems);
        const tierIndex = TIERS.indexOf(tier);
        const isCurrentUser = getCurrentUsername() === username;
        const bioText = profile ? (profile.bio || '') : '';
        let avatarUrl = profile ? profile.avatar_url : null;
        if (!avatarUrl && profile) {
            avatarUrl = randomAvatarUrl();
            await supabaseClient.from('user_profiles').update({ avatar_url: avatarUrl }).eq('username', username);
        }
        let progressHtml = '';
        if (nextTier) {
            const pct = Math.min(100, Math.round(((gems - tier.min) / (nextTier.min - tier.min)) * 100));
            const remaining = Math.max(0, nextTier.min - gems);
            progressHtml = `
            <div class="tier-progress">
                <div class="tier-progress-label">${tier.name} → ${nextTier.name} · ${remaining} more gems needed</div>
                <canvas id="tier-progress-canvas" width="260" height="8" aria-label="Tier progress"></canvas>
            </div>`;
        } else {
            progressHtml = `<div class="tier-progress"><div class="tier-progress-label">${tier.name} — Max tier reached (${gems} gems)</div></div>`;
        }
        let badgesHtml = '';
        if (badges && badges.length > 0) {
            badgesHtml = '<div class="profile-badges-grid">' + badges.map(b => `<span class="profile-badge-item" title="${b.badge_name}: ${b.badge_description || ''}">${badgeIconSvg(b.badge_key || 'insightful', '#3b82f6')} ${b.badge_name}</span>`).join('') + '</div>';
        } else {
            badgesHtml = '<p style="color:#000;font-size:12px;">No badges earned yet.</p>';
        }
        let postsHtml = posts ? posts.map(p => {
            const netVotes = getNetVotes(p);
            return `<div style="padding: 8px 0; border-bottom: 1px solid #e5e5e5;">
                <a class="profile-post-link" href="javascript:void(0);" onclick="navigatePost(${p.id})">${p.title}</a> <span style="color: #828282; font-size: 12px;">(${netVotes} pts)</span>
            </div>`;
        }).join('') : '';
        contentDiv.innerHTML = `
        <div class="surface-panel" style="padding:20px;">
            <div class="profile-header">
                ${avatarUrl ? `<img class="profile-avatar" src="${avatarUrl}" alt="${username}" />` : ''}
                <div>
                    <div class="profile-name-row">
                        <h2 style="margin: 0 0 4px 0;">${username}</h2>
                        ${tierBadgeHtml(tier)}
                    </div>
                    <span class="profile-tier-name" style="color:${tier.color};">${tier.name}</span>
                </div>
            </div>
            <div class="profile-bio">
                ${isCurrentUser
                    ? `<textarea id="bio-input" rows="3" class="comment-textarea" placeholder="Add a short bio...">${bioText}</textarea>
                       <button class="submit-btn" style="margin-top:8px;" onclick="saveBio('${username}')">Save bio</button>`
                    : `<p style="margin: 8px 0; color:#555;">${bioText || 'No bio yet.'}</p>`}
            </div>
            ${progressHtml}
            <div class="profile-stats">
                <div class="profile-stat"><strong>${posts ? posts.length : 0}</strong><span>${postsIconSvg()} Posts</span></div>
                <div class="profile-stat"><strong>${profile ? profile.contribution_points : 0}</strong><span>${pointsIconSvg()} Points</span></div>
                <div class="profile-stat"><strong>${gems}</strong><span>${gemIconSvg()} Gems</span></div>
                <div class="profile-stat"><strong>${profile ? (profile.rank || tierIndex) : 0}</strong><span>${rankIconSvg()} Rank</span></div>
            </div>
            <h3 style="margin: 16px 0 8px 0; font-size: 14px;">Badges</h3>
            ${badgesHtml}
            <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 16px 0;">
            <h3 style="margin: 12px 0 8px 0; font-size: 14px;">Recent Posts</h3>
            ${postsHtml || '<p style="color: #828282; font-size: 12px;">No posts.</p>'}
            <div style="margin-top: 20px;">
                <a href="javascript:void(0);" onclick="navigate('top')" style="font-size: 13px; color: #111; text-decoration: underline;">Back</a>
            </div>
        </div>`;
        if (nextTier) {
            const pct = Math.min(100, Math.round(((gems - tier.min) / (nextTier.min - tier.min)) * 100));
            requestAnimationFrame(() => drawTierProgress('tier-progress-canvas', pct, tier.color));
        }
    } catch (err) {
        console.error(err);
        contentDiv.innerHTML = '<p class="info" style="text-align:center; color: red;">Error loading profile.</p>';
    } finally {
        setLogoLoading(false);
    }
}

window.addEventListener('DOMContentLoaded', () => {
    Promise.resolve(initModeration()).then(() => {
        preloadPageBackground();
        checkAuth();
        handleRoute();
    });
});



