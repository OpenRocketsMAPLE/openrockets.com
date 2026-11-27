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


});
