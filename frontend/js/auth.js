async function checkAuth() {
    try {
        const res = await fetch('http://127.0.0.1:8000/accounts/me/', {
            credentials: 'include'
        });
        
        if (res.ok) {
            const data = await res.json();
            updateNavbar(data.user);
            return data.user;
        } else {
            updateNavbar(null);
            return null;
        }
    } catch (err) {
        console.error("Auth check failed:", err);
        updateNavbar(null);
        return null;
    }
}

function updateNavbar(user) {
    const navLinks = document.getElementById('nav-links-container');
    if (!navLinks) return;

    if (user) {
        navLinks.innerHTML = `
            <div class="user-badge">
                <span class="user-avatar">👤</span>
                <span class="user-name">${user.full_name}</span>
            </div>
            <a href="my-bookings.html" class="nav-btn">My Bookings</a>
            <button onclick="logout()" class="nav-btn btn-danger-outline">Logout</button>
        `;
    } else {
        navLinks.innerHTML = `
            <a href="login.html" class="nav-btn btn-primary-outline">Login</a>
            <a href="register.html" class="nav-btn btn-primary">Sign Up</a>
        `;
    }
}

async function logout() {
    try {
        await fetch('http://127.0.0.1:8000/accounts/logout/', {
            method: 'POST',
            credentials: 'include'
        });
        window.location.href = 'index.html';
    } catch (err) {
        console.error("Logout failed:", err);
    }
}

// Run auth check on page load if the container exists
document.addEventListener("DOMContentLoaded", () => {
    checkAuth();
});
