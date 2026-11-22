document.addEventListener('DOMContentLoaded', () => {
  renderCartPage();
});

function renderCartPage() {
  const cartContainer = document.getElementById('cart-container');
  if (!cartContainer) return;

  const currentCart = JSON.parse(localStorage.getItem('cart')) || [];
  const itemCount = currentCart.reduce((sum, item) => sum + item.quantity, 0);

  if (currentCart.length === 0) {
    cartContainer.innerHTML = `
      <div class="merch-empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
        <h1>Your cart is empty</h1>
        <p>Looks like you haven't added anything to your cart yet.</p>
        <a href="index.html" class="btn-primary" style="margin-top:16px;">Continue Shopping</a>
      </div>
    `;
    return;
  }

  const subtotal = currentCart.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const shipping = subtotal > 50 ? 0 : 9.99;
  const tax = subtotal * 0.08;
  const total = subtotal + shipping + tax;

  let cartItemsHTML = currentCart.map((item, index) => {
    return `
      <div class="merch-cart-item">
        <img src="${item.image}" alt="${item.name}" class="merch-cart-item-img" />
        <div class="merch-cart-item-info">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
            <div>
              <h2 class="merch-cart-item-name">${item.name}</h2>
              <p class="merch-cart-item-price-unit">$${item.price.toFixed(2)} each</p>
            </div>
            <button onclick="cartAction('remove', ${item.id})" class="btn-icon" style="color:var(--or-gray-400);border-color:transparent;" title="Remove">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>
            </button>
          </div>
          <div class="merch-cart-item-row">
            <div class="merch-qty-control" style="height:32px;">
              <button onclick="cartAction('decrease', ${item.id})" ${item.quantity <= 1 ? 'disabled' : ''} style="width:32px;height:32px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg>
              </button>
              <div class="merch-qty-display" style="min-width:40px;font-size:13px;">${item.quantity}</div>
              <button onclick="cartAction('increase', ${item.id})" style="width:32px;height:32px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              </button>
            </div>
            <div class="merch-cart-item-total">$${(item.price * item.quantity).toFixed(2)}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  cartContainer.innerHTML = `
    <div class="merch-cart-page">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:32px;flex-wrap:wrap;gap:16px;">
        <div>
          <h1 style="font-size:28px;font-weight:700;margin:0;font-family:var(--or-heading-font);">Shopping Cart</h1>
          <p style="color:var(--or-muted);margin:4px 0 0;">${itemCount} ${itemCount === 1 ? 'item' : 'items'} in your cart</p>
        </div>
        <a href="index.html" class="btn-ghost">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
          Continue Shopping
        </a>
      </div>

      <div class="merch-cart-layout">
        <div class="merch-cart-card">
          <div class="merch-cart-card-header">
            <h2>Cart Items</h2>
            <button onclick="cartAction('clear')" class="btn-ghost" style="color:#000000;font-size:13px;padding:4px 8px;">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
              Clear All
            </button>
          </div>
          <div class="merch-cart-card-body">
            ${cartItemsHTML}
          </div>
        </div>

        <div class="merch-summary-card">
          <div class="merch-summary-header">Order Summary</div>
          <div class="merch-summary-body">
            <div class="merch-summary-row">
              <span class="label">Subtotal</span>
              <span class="value">$${subtotal.toFixed(2)}</span>
            </div>
            <div class="merch-summary-row">
              <span class="label">Shipping</span>
              <span class="value">${shipping === 0 ? '<span style="font-size:12px;font-weight:600;background:var(--or-gray-100);padding:2px 6px;border-radius:4px;">Free</span>' : '$' + shipping.toFixed(2)}</span>
            </div>
            <div class="merch-summary-row">
              <span class="label">Tax</span>
              <span class="value">$${tax.toFixed(2)}</span>
            </div>
            <div class="merch-summary-row total">
              <span>Total</span>
              <span>$${total.toFixed(2)}</span>
            </div>

            ${shipping > 0 ? `
              <div style="background:var(--or-gray-50);border:1px solid var(--or-border);border-radius:8px;padding:12px;margin-top:8px;">
                <p style="font-size:13px;font-weight:600;margin:0 0 4px;">Free shipping over $50</p>
                <p style="font-size:12px;color:var(--or-muted);margin:0;">Add $${(50 - subtotal).toFixed(2)} more to qualify!</p>
              </div>
            ` : ''}

            <button id="btn-checkout" onclick="cartAction('checkout')" class="btn-primary merch-checkout-btn" style="margin-top:16px;">
              Proceed to Checkout
            </button>
            
            <!-- Kept Warranty / Shipping texts as requested -->
            <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--or-border);display:flex;flex-direction:column;gap:12px;">
              <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--or-muted);">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--or-black);"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2-1 4-2 7-2 2 0 2 0 2 0a1 1 0 0 1 1 1v6Z"/></svg>
                Secure Checkout & 1-Year Warranty
              </div>
              <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--or-muted);">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--or-black);"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>
                Free returns within 30 days
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  `;
}

window.cartAction = function(action, id) {
  if (action === 'clear') {
    clearCart();
  } else if (action === 'remove') {
    removeFromCart(id);
  } else if (action === 'decrease') {
    const item = cart.find(c => c.id === id);
    if (item) updateQuantity(id, item.quantity - 1);
  } else if (action === 'increase') {
    const item = cart.find(c => c.id === id);
    if (item) updateQuantity(id, item.quantity + 1);
  } else if (action === 'checkout') {
    const btn = document.getElementById('btn-checkout');
    if (btn) {
      btn.innerHTML = `
        <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        Processing...
      `;
      btn.disabled = true;
      setTimeout(() => {
        clearCart();
        btn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px;"><path d="M20 6 9 17l-5-5"/></svg>
          Order Placed!
        `;
        btn.style.background = '#000000';
        setTimeout(() => {
          renderCartPage();
        }, 1500);
      }, 1500);
      return; 
    }
  }
  
  renderCartPage();
};
