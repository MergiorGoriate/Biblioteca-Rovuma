const form = document.querySelector('#upload');
const meter = document.querySelector('#transfer');
const status = document.querySelector('#upload-status');

async function request(url, body) {
    const response = await fetch(url, {method: body ? 'POST' : 'GET', body, credentials: 'same-origin'});
    const json = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {};
    if (!response.ok && response.status !== 409) {
        const error = new Error(json.error || 'A ligação foi interrompida ou a sessão expirou.');
        error.status = response.status;
        throw error;
    }
    return json;
}

form.addEventListener('submit', async event => {
    event.preventDefault();
    const file = document.querySelector('#source').files[0];
    if (!file) return;
    const data = new FormData(form);
    const token = data.get('csrfmiddlewaretoken');
    const button = form.querySelector('button');
    button.disabled = true;
    meter.hidden = false;
    status.textContent = 'A preparar o carregamento…';
    try {
        const sample = new Uint8Array(await file.slice(0, 65536).arrayBuffer());
        const tail = new Uint8Array(await file.slice(-65536).arrayBuffer());
        const fingerprint = new Uint8Array(sample.length + tail.length);
        fingerprint.set(sample);
        fingerprint.set(tail, sample.length);
        const metadata = new TextEncoder().encode(JSON.stringify([file.name, file.size, file.lastModified,
            data.get('mode'), data.get('authorization')]));
        const framed = new Uint8Array(metadata.length + fingerprint.length);
        framed.set(metadata);
        framed.set(fingerprint, metadata.length);
        const digest = await crypto.subtle.digest('SHA-256', framed);
        const signature = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
        const key = 'rovuma.upload.' + form.dataset.key + '.' + signature;
        let url = localStorage.getItem(key);
        let current;
        if (url) {
            try {
                current = await request(url);
            } catch (error) {
                if (error.status !== 404 && error.status !== 410) throw error;
                localStorage.removeItem(key);
                url = null;
            }
        }
        if (!url) {
            data.set('name', file.name);
            data.set('size', file.size);
            const started = await request(form.dataset.start, data);
            url = started.url;
            current = {offset: 0, chunk: started.chunk};
            localStorage.setItem(key, url);
        }
        let offset = current.offset;
        while (offset < file.size) {
            const payload = new FormData();
            payload.set('csrfmiddlewaretoken', token);
            payload.set('offset', offset);
            payload.set('chunk', file.slice(offset, offset + current.chunk), 'part');
            const result = await request(url, payload);
            if (!Number.isInteger(result.offset) || result.offset <= offset) {
                throw new Error(result.error || 'O servidor não confirmou esta parte.');
            }
            offset = result.offset;
            meter.value = Math.floor(100 * offset / file.size);
            status.textContent = meter.value + '% carregado';
        }
        const finish = new FormData();
        finish.set('csrfmiddlewaretoken', token);
        finish.set('finish', '1');
        const result = await request(url, finish);
        if (!result.next) throw new Error(result.error || 'Não foi possível concluir.');
        localStorage.removeItem(key);
        location.assign(result.next);
    } catch (error) {
        status.textContent = error.message + ' Para retomar, seleccione o mesmo ficheiro e mantenha os dados do formulário.';
    } finally {
        button.disabled = false;
    }
});
