const API = 'http://127.0.0.1:7332';

async function openSidePanel(windowId) {
  try {
    await chrome.sidePanel.open({ windowId });
  } catch (error) {
    console.warn('murn. side panel open failed', error);
  }
}

async function queuePrompt(prompt, context = {}) {
  await chrome.storage.session.set({
    pendingPrompt: {
      prompt,
      context,
      createdAt: Date.now(),
    },
  });
}

async function pageContext(tabId) {
  if (!tabId) return { ok: false, error: 'no active tab' };
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
        return {
          title: document.title,
          url: location.href,
          selection: clean(window.getSelection?.()?.toString?.() || '').slice(0, 6000),
          text: clean(document.body?.innerText || '').slice(0, 14000),
        };
      },
    });
    return { ok: true, ...(result?.result || {}) };
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab || null;
}

async function openMurnDesktop() {
  try {
    const response = await fetch(`${API}/v1/integration/open-murn`, { method: 'POST' });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  } catch (_) {}

  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: 'murn-selection',
      title: 'Ask murn. about “%s”',
      contexts: ['selection'],
    });
    chrome.contextMenus.create({
      id: 'murn-page',
      title: 'Analyze this page with murn.',
      contexts: ['page'],
    });
    chrome.contextMenus.create({
      id: 'murn-open-app',
      title: 'Open murn. desktop',
      contexts: ['page', 'selection', 'link'],
    });
  });
});

chrome.runtime.onStartup.addListener(async () => {
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  } catch (_) {}
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'murn-open-app') {
    await openMurnDesktop();
    return;
  }

  if (!tab?.windowId) return;
  if (info.menuItemId === 'murn-selection') {
    await queuePrompt(`Analisa esse trecho da página pra mim:\n\n${info.selectionText || ''}`, {
      title: tab.title || '',
      url: tab.url || '',
      selection: info.selectionText || '',
    });
    await openSidePanel(tab.windowId);
  }

  if (info.menuItemId === 'murn-page') {
    await queuePrompt('Analisa e resume a página que eu estou vendo.', {
      title: tab.title || '',
      url: tab.url || '',
      requestPageContext: true,
    });
    await openSidePanel(tab.windowId);
  }
});

chrome.omnibox.setDefaultSuggestion({
  description: 'Ask murn. — <match>%s</match>',
});

chrome.omnibox.onInputChanged.addListener((text, suggest) => {
  suggest([
    { content: text, description: `Ask murn. → <match>${text}</match>` },
    { content: `search web: ${text}`, description: `murn. web research → <match>${text}</match>` },
  ]);
});

chrome.omnibox.onInputEntered.addListener(async (text) => {
  const tab = await activeTab();
  if (!tab?.windowId) return;
  const prompt = text.startsWith('search web: ')
    ? `Pesquisa na internet: ${text.slice('search web: '.length)}`
    : text;
  await queuePrompt(prompt, { title: tab.title || '', url: tab.url || '' });
  await openSidePanel(tab.windowId);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'page-context') {
    (async () => {
      const tab = await activeTab();
      const context = await pageContext(tab?.id);
      sendResponse({ ...context, tabId: tab?.id, windowId: tab?.windowId });
    })();
    return true;
  }

  if (message?.type === 'open-murn') {
    openMurnDesktop().then(sendResponse);
    return true;
  }

  if (message?.type === 'search') {
    chrome.search.query({
      text: String(message.text || ''),
      disposition: message.disposition || 'CURRENT_TAB',
    }).then(() => sendResponse({ ok: true })).catch((error) => {
      sendResponse({ ok: false, error: String(error) });
    });
    return true;
  }

  return false;
});
