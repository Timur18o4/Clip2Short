async function() {
    // This command has no chat response and is invoked only by the local service.
    let claimed = false;
    let stage = '';
    let id = '';
    let base = '';
    let key = '';
    let analysisKind = 'main';
    const request = async function(path, value, method) {
        const options = {
            method: method || 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key },
            signal: AbortSignal.timeout(20000)
        };
        if (value !== undefined) options.body = JSON.stringify(value);
        const response = await fetch(base + path, options);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Lokaler Dienst nicht erreichbar.');
        return data;
    };
    try {
        const origin = await getVariable('originType');
        if (origin !== 'api') { done(); return; }
        stage = String(await getVariable('clip2short_stage') || '');
        id = String(await getVariable('clip2short_clip_id') || '');
        base = String(await getVariable('clip2short_service_url') || '');
        key = String(await getVariable('clip2short_bridge_key') || '');
        if (base !== 'http://127.0.0.1:39242' || key.length < 24) throw new Error('Dienstverbindung fehlt.');
        if (stage === 'check') {
            const token = await getToken('twitch');
            const client = await getClientId('twitch');
            const response = await fetch('https://id.twitch.tv/oauth2/validate', {
                headers: { Authorization: 'OAuth ' + token }, signal: AbortSignal.timeout(15000)
            });
            if (!response.ok) throw new Error('Twitch-Anmeldung in Lumia prüfen.');
            const auth = await response.json();
            const scope = (auth.scopes || []).some(function(s) { return s === 'channel:manage:clips' || s === 'editor:manage:clips'; });
            const probe = await resolveVariables('{' + '{ai_prompt=Antworte ausschließlich mit CLIP2SHORT_OK.}' + '}');
            await request('/api/diagnostic', {
                message: 'Lumia-Befehl erreichbar. Twitch: ' + String(auth.login) + '. KI: ' + (String(probe).trim() === 'CLIP2SHORT_OK') + '. Download erfolgt separat für den neuen öffentlichen Clip.',
                twitch_login: auth.login, clip_download_scope: scope,
                ai_ok: String(probe).trim() === 'CLIP2SHORT_OK', tiktok_username: String(await getVariable('tiktok_username') || '')
            });
        } else if (stage === 'resolve') {
            if (!/^[A-Za-z0-9_-]{8,200}$/.test(id)) throw new Error('Clip-ID fehlt.');
            const token = await getToken('twitch');
            const client = await getClientId('twitch');
            if (!token || !client) throw new Error('Twitch ist in Lumia nicht angemeldet.');
            const helix = async function(path) {
                const response = await fetch('https://api.twitch.tv/helix/' + path, {
                    headers: { Authorization: 'Bearer ' + token, 'Client-ID': client }, signal: AbortSignal.timeout(20000)
                });
                if (!response.ok) {
                    if (response.status === 403) throw new Error('Lumia-Twitch-Anmeldung benötigt channel:manage:clips für offizielle Clip-Downloads.');
                    throw new Error('Twitch-Anfrage fehlgeschlagen (' + response.status + ').');
                }
                return await response.json();
            };
            let clip;
            for (let i = 0; i < 8; i++) {
                const clips = await helix('clips?id=' + encodeURIComponent(id));
                clip = clips.data && clips.data[0];
                if (clip) break;
                await delay(1500);
            }
            if (!clip) throw new Error('Neuer Clip ist bei Twitch noch nicht abrufbar.');
            // Validate creation time BEFORE requesting or fetching media.
            const eligibility = await request('/api/eligible', { clip: clip });
            if (!eligibility.eligible) { log('Clip2Short: Clip ausgeschlossen: ' + eligibility.reason); done(); return; }
            const games = await helix('games?id=' + encodeURIComponent(clip.game_id));
            const category = games.data && games.data[0] && games.data[0].name;
            if (!category) throw new Error('Kategorie dieses Clips konnte nicht ermittelt werden.');
            let streamTitle = String(await getVariable('clip2short_stream_title') || '');
            if (clip.video_id) {
                try {
                    const videos = await helix('videos?id=' + encodeURIComponent(clip.video_id));
                    if (videos.data && videos.data[0]) streamTitle = String(videos.data[0].title || streamTitle);
                } catch (_) { /* A removed VOD must not block a new public clip. */ }
            }
            await request('/api/resolved', {
                clip: clip, category: category, stream_title: streamTitle
            });
        } else if (stage === 'editorial') {
            analysisKind = String(await getVariable('clip2short_analysis_kind') || 'main');
            const job = await request('/api/jobs/' + encodeURIComponent(id), undefined, 'GET');
            const prefix = analysisKind === 'preview' ? 'preview_' : '';
            const context = job[prefix + 'editorial_context'];
            if (!context || !job[prefix + 'editorial_prompt']) throw new Error('Titelkontext fehlt.');
            let lastError = '';
            let accepted = false;
            for (let attempt = 0; attempt < 2; attempt++) {
                const instruction = job[prefix + 'editorial_prompt'] + (lastError ? '\nKorrigiere: ' + lastError : '');
                const result = await resolveVariables('{' + '{ai_prompt=' + instruction + '}' + '}');
                try {
                    await request('/api/editorial', { id: id, kind: analysisKind, analysis_key: context.key, result: String(result) });
                    accepted = true; break;
                } catch (error) { lastError = String(error.message || error); }
            }
            if (!accepted) throw new Error(lastError || 'Titel und Chatbezug konnten nicht geprüft werden.');
        } else if (stage === 'publish') {
            const job = await request('/api/jobs/' + encodeURIComponent(id), undefined, 'GET');
            if (job.state !== 'ready') { done(); return; }
            let claim;
            let lastError = '';
            for (let attempt = 0; attempt < 2; attempt++) {
                const instruction = job.prompt + (lastError ? '\nKorrigiere diese Ausgabeanforderung: ' + lastError : '');
                const caption = await resolveVariables('{' + '{ai_prompt=' + instruction + '}' + '}');
                try { claim = await request('/api/claim', { id: id, caption: String(caption) }); break; }
                catch (error) { lastError = String(error.message || error); }
            }
            if (!claim) throw new Error(lastError || 'KI-Beschreibung ist ungültig.');
            if (!claim.claimed) { done(); return; }
            claimed = true;
            if (claim.privacy !== 'SELF_ONLY' && claim.privacy !== 'PUBLIC_TO_EVERYONE') throw new Error('Unbekannte Sichtbarkeit.');
            const beforeLink = String(await getVariable('tiktok_last_video_link') || '');
            const result = await actions([{
                base: 'tiktok', type: 'uploadAndPublishVideo',
                value: {
                    media: claim.media, title: claim.caption, privacy_level: claim.privacy,
                    disable_comment: false, disable_duet: false, disable_stitch: false
                }
            }]);
            const afterLink = String(await getVariable('tiktok_last_video_link') || '');
            // Awaited action completion is not proof of TikTok's processing result.
            await request('/api/result', { id: id, result: result === undefined ? null : result, url: afterLink !== beforeLink ? afterLink : '' });
            log('Clip2Short: TikTok-Aufruf für ' + id + ' durch Lumia abgeschlossen (' + claim.privacy + ').');
        } else {
            throw new Error('Unbekannter Clip2Short-Dienstschritt.');
        }
    } catch (error) {
        const message = String(error && error.message || error).slice(0, 500);
        log('Clip2Short: ' + message);
        if (base && key) {
            try {
                await request(claimed ? '/api/result' : '/api/diagnostic', claimed ? { id: id, error: message } : { message: message, stage: stage, id: id, kind: analysisKind });
            } catch (_) { /* A claimed upload stays blocked in the service journal. */ }
        }
    }
    done();
}
