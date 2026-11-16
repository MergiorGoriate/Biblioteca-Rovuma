import {getDocument, GlobalWorkerOptions} from './vendor/legacy/build/pdf.mjs';

const root = document.querySelector('#reader');
const asset = root.dataset.assets;
GlobalWorkerOptions.workerSrc = asset + 'legacy/build/pdf.worker.mjs';
const canvas = document.querySelector('#page-canvas');
const wrap = document.querySelector('#canvas-wrap');
const pageInput = document.querySelector('#page');
const status = document.querySelector('#reader-status');
const transcript = document.querySelector('#page-text');
const marker = document.querySelector('#marker');
const token = document.querySelector('[name=csrfmiddlewaretoken]').value;
const previous = document.querySelector('#previous');
const next = document.querySelector('#next');
let doc, activeRender;
let page = Number(root.dataset.page);
let zoom = null;
let revision = 0;
let feedback = '';
let lastFit = 1;
let persistence = Promise.resolve();

async function persist(action, number) {
    if (!root.dataset.update) return;
    const response = await fetch(root.dataset.update, {
        method: 'POST', credentials: 'same-origin',
        body: new URLSearchParams({csrfmiddlewaretoken: token, action, page: number}),
    });
    if (!response.ok || response.redirected) throw new Error('Não foi possível guardar a leitura.');
    const result = await response.json();
    if (marker && page === number) {
        marker.setAttribute('aria-pressed', String(result.marked));
        marker.textContent = result.marked ? 'Remover marcador' : 'Guardar marcador';
    }
}
function queue(action, number) {
    persistence = persistence.catch(() => {}).then(() => persist(action, number));
    persistence.catch(error => { status.textContent = error.message; });
}

async function show(number, save = true) {
    if (!doc) return;
    page = Math.max(1, Math.min(doc.numPages, number || 1));
    pageInput.value = page;
    previous.disabled = page === 1;
    next.disabled = page === doc.numPages;
    if (marker) marker.disabled = true;
    const serial = ++revision;
    if (activeRender) {
        activeRender.cancel();
        await activeRender.promise.catch(() => {});
    }
    try {
        const item = await doc.getPage(page);
        if (serial !== revision) return;
        const initial = item.getViewport({scale: 1});
        const fit = Math.min(2, (wrap.clientWidth - 16) / initial.width);
        lastFit = fit;
        const logical = item.getViewport({scale: zoom ?? fit});
        const ratio = Math.max(0.2, Math.min(devicePixelRatio || 1, 2, Math.sqrt(12_000_000 / (logical.width * logical.height))));
        canvas.width = Math.max(1, Math.floor(logical.width * ratio));
        canvas.height = Math.max(1, Math.floor(logical.height * ratio));
        canvas.style.width = logical.width + 'px';
        canvas.style.height = logical.height + 'px';
        activeRender = item.render({canvas, viewport: logical, transform: [ratio, 0, 0, ratio, 0, 0]});
        await activeRender.promise;
        if (serial !== revision) return;
        status.textContent = feedback || 'Página ' + page + ' de ' + doc.numPages;
        if (marker) marker.disabled = false;
        if (save) queue('progress', page);
        const content = await item.getTextContent();
        if (serial === revision) transcript.textContent = content.items.map(entry => entry.str || '').join(' ') || 'Esta página não tem texto seleccionável.';
    } catch (error) {
        if (serial === revision && error.name !== 'RenderingCancelledException') {
            status.textContent = 'Não foi possível mostrar a página. Verifique a ligação e a sessão.';
        }
    }
}

function navigate(number) {
    feedback = '';
    show(number);
}
previous.addEventListener('click', () => navigate(page - 1));
next.addEventListener('click', () => navigate(page + 1));
pageInput.addEventListener('change', () => navigate(Number(pageInput.value)));
document.querySelector('#fit').addEventListener('click', () => { zoom = null; show(page, false); });
document.querySelector('#zoom-in').addEventListener('click', () => { zoom = Math.min(4, (zoom ?? lastFit) * 1.25); show(page, false); });
document.querySelector('#zoom-out').addEventListener('click', () => { zoom = Math.max(.25, (zoom ?? lastFit) / 1.25); show(page, false); });
if (marker) marker.addEventListener('click', () => queue(marker.getAttribute('aria-pressed') === 'true' ? 'unmark' : 'mark', page));
let resize;
window.addEventListener('resize', () => {
    clearTimeout(resize);
    if (zoom === null) resize = setTimeout(() => show(page, false), 150);
});

function normalise(value) {
    return value.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('pt');
}
let searchNumber = 0;
document.querySelector('#pdf-search').addEventListener('submit', async event => {
    event.preventDefault();
    if (!doc) return;
    const query = normalise(document.querySelector('#pdf-query').value.trim());
    if (!query) return;
    const search = ++searchNumber;
    const first = page;
    status.textContent = 'A procurar texto…';
    try {
        for (let offset = 1; offset <= doc.numPages; offset++) {
            if (search !== searchNumber) return;
            const candidate = ((first + offset - 1) % doc.numPages) + 1;
            const content = await (await doc.getPage(candidate)).getTextContent();
            if (search !== searchNumber) return;
            if (normalise(content.items.map(item => item.str || '').join(' ')).includes(query)) {
                feedback = 'Texto encontrado na página ' + candidate + '.';
                show(candidate);
                return;
            }
        }
        status.textContent = 'Sem resultados no texto seleccionável do PDF.';
    } catch {
        status.textContent = 'Não foi possível concluir a pesquisa.';
    }
});

try {
    doc = await getDocument({
        url: root.dataset.pdf, cMapUrl: asset + 'cmaps/', cMapPacked: true,
        standardFontDataUrl: asset + 'standard_fonts/', wasmUrl: asset + 'wasm/',
        disableAutoFetch: true, disableStream: true, isEvalSupported: false, useWasm: false,
    }).promise;
    document.querySelector('#page-total').textContent = '/ ' + doc.numPages;
    show(page);
} catch {
    status.textContent = 'O documento não abriu. Verifique a ligação ou volte a iniciar sessão.';
}
