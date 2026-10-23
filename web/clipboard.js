// Keep the exact text available when a browser cannot write to the clipboard.
export async function copyText(text, {clipboard, dialog, field}) {
  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    // PDF text and links are plain text, never markup to render.
    field.value = text;
    if (!dialog.open) dialog.showModal();
    field.focus();
    field.select();
    return false;
  }
}
