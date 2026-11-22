document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const q = params.get('q');
  
  if (q) {
    const searchDesktop = document.getElementById('search-desktop');
    const searchMobile = document.getElementById('search-mobile');
    if (searchDesktop) searchDesktop.value = q;
    if (searchMobile) searchMobile.value = q;
    filterProducts(q);
  } else {
    renderProducts(products);
  }

  const searchDesktop = document.getElementById('search-desktop');
  if (searchDesktop) {
    searchDesktop.addEventListener('input', (e) => filterProducts(e.target.value));
  }
  
  const searchMobile = document.getElementById('search-mobile');
  if (searchMobile) {
    searchMobile.addEventListener('input', (e) => filterProducts(e.target.value));
  }
});

function filterProducts(term) {
  term = term.toLowerCase();
  const filtered = products.filter(p => p.name.toLowerCase().includes(term) || p.description.toLowerCase().includes(term));
  renderProducts(filtered);
}

function renderProducts(productArray) {
  const productContainer = document.getElementById('product-list');
  if (!productContainer) return;
  productContainer.innerHTML = '';
  
  if (productArray.length > 0) {
    productArray.forEach(product => {
      const card = document.createElement('div');
      card.className = "merch-product-card group";
      card.innerHTML = `
        <a href="product.html?id=${product.id}" class="merch-card-img-wrap block">
          <img src="${product.image}" alt="${product.name}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
          <div class="merch-card-overlay">
            <span class="btn-primary" style="pointer-events:none;">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>
              View Details
            </span>
          </div>
        </a>
        <div class="merch-card-body">
          <a href="product.html?id=${product.id}" style="text-decoration:none;">
            <h2 class="merch-card-name">${product.name}</h2>
          </a>
          <p class="merch-card-price">$${product.price.toFixed(2)}</p>
          <div style="margin-top:auto;padding-top:8px;">
            <button class="btn-primary" style="width:100%;" onclick="handleAddToCart(this, ${product.id}, event)">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
              Add to Cart
            </button>
          </div>
        </div>
      `;
      productContainer.appendChild(card);
    });
  } else {
    productContainer.innerHTML = `
      <div class="merch-no-results">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:#000000;margin-bottom:16px;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <h3>No products found</h3>
        <p>Try adjusting your search term.</p>
      </div>
    `;
  }
}

function handleAddToCart(btn, productId, event) {
  event.preventDefault();
  event.stopPropagation();

  if (btn.disabled) return;
  btn.disabled = true;
  const originalContent = btn.innerHTML;
  
  btn.innerHTML = `
    <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
    Adding...
  `;

  const product = products.find(p => p.id === productId);

  setTimeout(() => {
    addToCart({
      id: product.id,
      name: product.name,
      price: product.price,
      image: product.image
    });

    btn.style.background = '#000000';
    btn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
      Added!
    `;

    setTimeout(() => {
      btn.style.background = '';
      btn.innerHTML = originalContent;
      btn.disabled = false;
    }, 2000);
  }, 300);
}
