document.addEventListener('DOMContentLoaded', () => {
  renderProductPage();
});

function renderProductPage() {
  const container = document.getElementById('product-container');
  if (!container) return;

  const params = new URLSearchParams(window.location.search);
  const productId = parseInt(params.get('id'));
  const product = products.find(p => p.id === productId);

  if (!product) {
    container.innerHTML = `
      <div class="merch-empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <h1>Product Not Found</h1>
        <p>This item doesn't exist or has been removed.</p>
        <a href="index.html" class="btn-primary">Return to Shop</a>
      </div>
    `;
    return;
  }

  let quantity = 1;

  container.innerHTML = `
    <div class="merch-product-detail">
      <nav style="margin-bottom:32px;">
        <a href="index.html" class="btn-ghost">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>
          Back to Shop
        </a>
      </nav>

      <div class="merch-detail-grid">
        <div class="merch-detail-image">
          <img src="${product.image}" alt="${product.name}" />
        </div>

        <div class="merch-detail-info">
          <h1 class="merch-detail-name">${product.name}</h1>
          <p class="merch-detail-price">$${product.price.toFixed(2)}</p>
          <p class="merch-detail-desc">${product.description}</p>
          
          <hr class="merch-divider" style="margin:8px 0;" />

          <div>
            <label style="display:block;font-size:14px;font-weight:600;margin-bottom:8px;">Quantity</label>
            <div class="merch-qty-control">
              <button id="btn-decrease" ${quantity <= 1 ? 'disabled' : ''}>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg>
              </button>
              <div id="quantity-display" class="merch-qty-display">${quantity}</div>
              <button id="btn-increase">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              </button>
            </div>
          </div>

          <div class="merch-action-row" style="margin-top:16px;">
            <button id="btn-add-cart" class="btn-primary">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
              Add to Cart
            </button>
            <button id="btn-buy-now" class="btn-secondary">Buy Now</button>
          </div>
        </div>
      </div>

      <!-- Related Products -->
      <div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
          <h2 style="font-size:24px;font-weight:700;margin:0;font-family:var(--or-heading-font);">You might also like</h2>
          <a href="index.html" class="btn-ghost">View All</a>
        </div>
        <div class="merch-related-grid">
          ${products.filter(p => p.id !== product.id).slice(0, 4).map(rp => `
            <div class="merch-product-card" style="border-color:#000000;">
              <a href="product.html?id=${rp.id}" class="merch-card-img-wrap block">
                <img src="${rp.image}" alt="${rp.name}" />
              </a>
              <div class="merch-card-body" style="padding:12px;">
                <a href="product.html?id=${rp.id}" style="text-decoration:none;">
                  <h3 class="merch-card-name" style="font-size:13px;">${rp.name}</h3>
                </a>
                <p class="merch-card-price" style="font-size:14px;margin-top:4px;">$${rp.price.toFixed(2)}</p>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;

  // Attach event listeners
  const btnDecrease = document.getElementById('btn-decrease');
  const btnIncrease = document.getElementById('btn-increase');
  const quantityDisplay = document.getElementById('quantity-display');
  const btnAddCart = document.getElementById('btn-add-cart');
  const btnBuyNow = document.getElementById('btn-buy-now');
  
  btnDecrease.addEventListener('click', () => {
    if (quantity > 1) {
      quantity--;
      quantityDisplay.textContent = quantity;
      btnDecrease.disabled = quantity <= 1;
    }
  });

  btnIncrease.addEventListener('click', () => {
    quantity++;
    quantityDisplay.textContent = quantity;
    btnDecrease.disabled = false;
  });

  btnAddCart.addEventListener('click', () => {
    if (btnAddCart.disabled) return;
    btnAddCart.disabled = true;
    const originalContent = btnAddCart.innerHTML;
    
    btnAddCart.innerHTML = `
      <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
      Adding...
    `;

    setTimeout(() => {
      addToCart({
        id: product.id,
        name: product.name,
        price: product.price,
        image: product.image
      }, quantity);

      btnAddCart.style.background = '#000000';
      btnAddCart.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
        Added to Cart!
      `;

      setTimeout(() => {
        btnAddCart.style.background = '';
        btnAddCart.innerHTML = originalContent;
        btnAddCart.disabled = false;
      }, 2000);
    }, 300);
  });

  btnBuyNow.addEventListener('click', () => {
    addToCart({
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image
    }, quantity);
    window.location.href = 'cart.html';
  });
}
