// Cart logic for the static site
let cart = JSON.parse(localStorage.getItem("cart")) || [];

function saveCart() {
  localStorage.setItem("cart", JSON.stringify(cart));
  updateCartBadge();
}

function addToCart(item, quantity = 1) {
  const existingItem = cart.find(c => c.id === item.id);
  if (existingItem) {
    existingItem.quantity += quantity;
  } else {
    cart.push({ ...item, quantity });
  }
  saveCart();
}

function removeFromCart(id) {
  cart = cart.filter(item => item.id !== id);
  saveCart();
}

function updateQuantity(id, quantity) {
  const item = cart.find(c => c.id === id);
  if (item) {
    item.quantity = Math.max(1, quantity);
    saveCart();
  }
}

function clearCart() {
  cart = [];
  saveCart();
}

function getCartCount() {
  return cart.reduce((total, item) => total + item.quantity, 0);
}

function updateCartBadge() {
  const badgeContainers = document.querySelectorAll('.cart-badge-container');
  const count = getCartCount();
  
  badgeContainers.forEach(container => {
    // We expect the container to hold the badge if count > 0
    let badge = container.querySelector('.cart-badge');
    if (count > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'cart-badge absolute -top-1 -right-1 bg-primary text-white text-xs font-bold rounded-full min-w-[20px] h-5 flex items-center justify-center px-1';
        container.appendChild(badge);
      }
      badge.textContent = count > 99 ? "99+" : count;
      badge.setAttribute('aria-label', `${count} items in cart`);
    } else {
      if (badge) {
        badge.remove();
      }
    }
  });
}

// Layout common scripts (Header interactions)
document.addEventListener('DOMContentLoaded', () => {
  updateCartBadge();

  // Scroll effect on header
  const header = document.querySelector('header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 10) {
      header.classList.add('bg-white/95', 'backdrop-blur-xl', 'border-b', 'border-gray-200', 'shadow-lg');
      header.classList.remove('bg-white/80', 'backdrop-blur-md', 'shadow-sm');
    } else {
      header.classList.remove('bg-white/95', 'backdrop-blur-xl', 'border-lg', 'shadow-lg');
      header.classList.add('bg-white/80', 'backdrop-blur-md', 'shadow-sm', 'border-b', 'border-gray-200');
    }
  });

  // Mobile menu toggle
  const mobileMenuBtn = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  const mobileMenuIcon = document.getElementById('mobile-menu-icon');

  if (mobileMenuBtn && mobileMenu) {
    mobileMenuBtn.addEventListener('click', () => {
      const isOpen = !mobileMenu.classList.contains('hidden');
      if (isOpen) {
        mobileMenu.classList.add('hidden');
        mobileMenuIcon.innerHTML = '<path d="M4 12h16M4 6h16M4 18h16"></path>'; // Menu icon
      } else {
        mobileMenu.classList.remove('hidden');
        mobileMenuIcon.innerHTML = '<path d="M18 6 6 18M6 6l12 12"></path>'; // X icon
      }
    });
  }

  // Mobile search toggle
  const mobileSearchBtn = document.getElementById('mobile-search-btn');
  const mobileSearch = document.getElementById('mobile-search');
  if (mobileSearchBtn && mobileSearch) {
    mobileSearchBtn.addEventListener('click', () => {
      mobileSearch.classList.toggle('hidden');
    });
  }
});
