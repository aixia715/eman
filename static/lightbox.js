const overlay = document.createElement('div');
overlay.className = 'lightbox hidden';
overlay.setAttribute('role', 'dialog');
overlay.setAttribute('aria-modal', 'true');
overlay.setAttribute('aria-label', '插图预览');

const close = document.createElement('button');
close.type = 'button';
close.className = 'lightbox-close';
close.textContent = '×';
close.setAttribute('aria-label', '关闭插图预览');

const previous = document.createElement('button');
previous.type = 'button';
previous.className = 'lightbox-nav lightbox-previous';
previous.textContent = '‹';
previous.setAttribute('aria-label', '上一张');

const next = document.createElement('button');
next.type = 'button';
next.className = 'lightbox-nav lightbox-next';
next.textContent = '›';
next.setAttribute('aria-label', '下一张');

const figure = document.createElement('figure');
const image = document.createElement('img');
const caption = document.createElement('figcaption');
figure.append(image, caption);
overlay.append(close, previous, figure, next);
document.body.appendChild(overlay);

let items = [];
let currentIndex = 0;

function render() {
  const item = items[currentIndex];
  if (!item) return;
  image.src = item.src;
  image.alt = item.alt || `插图 ${currentIndex + 1}`;
  caption.textContent = item.alt || `${currentIndex + 1} / ${items.length}`;
  previous.classList.toggle('hidden', items.length < 2);
  next.classList.toggle('hidden', items.length < 2);
}

function move(offset) {
  currentIndex = (currentIndex + offset + items.length) % items.length;
  render();
}

export function openLightbox(images, index = 0) {
  items = images;
  currentIndex = index;
  render();
  overlay.classList.remove('hidden');
  close.focus();
}

function closeLightbox() {
  overlay.classList.add('hidden');
  image.removeAttribute('src');
}

close.onclick = closeLightbox;
previous.onclick = () => move(-1);
next.onclick = () => move(1);
overlay.onclick = event => {
  if (event.target === overlay) closeLightbox();
};

document.addEventListener('keydown', event => {
  if (overlay.classList.contains('hidden')) return;
  event.stopImmediatePropagation();
  if (event.key === 'Escape') closeLightbox();
  else if (event.key === 'ArrowLeft' && items.length > 1) move(-1);
  else if (event.key === 'ArrowRight' && items.length > 1) move(1);
});
