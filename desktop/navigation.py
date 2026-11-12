"""One visible page and explicit resource ownership for the desktop shell."""
from tkinter import ttk


class PageHost(ttk.Frame):
    """Build pages lazily; leaving a page always revokes its resources."""

    def __init__(self, parent, builders):
        super().__init__(parent, style='DB.TFrame')
        self.builders = dict(builders)
        self.pages = {}
        self.current_key = None
        self._disposed = False
        self.bind('<Destroy>', self._on_destroy, add='+')

    def _on_destroy(self, event):
        if event.widget is self:
            self.dispose()

    def show_page(self, key, *, refresh=False):
        builder = self.builders[key]  # Validate before discarding usable content.
        if self._disposed:
            raise RuntimeError('Page host is disposed')
        if key == self.current_key and not refresh:
            return self.pages[key]
        self._clear()
        before = set(self.winfo_children())
        try:
            page = builder(self)
        except Exception:
            for child in set(self.winfo_children()) - before:
                try:
                    self._dispose_page(child)
                except Exception:
                    pass  # Preserve the original construction error.
            raise
        self.pages[key] = page
        self.current_key = key
        page.pack(fill='both', expand=True)
        self.event_generate('<<DroidBridgePageChanged>>')
        return page

    def _clear(self):
        pages, self.pages = self.pages, {}
        self.current_key = None
        error = None
        for page in pages.values():
            try:
                self._dispose_page(page)
            except Exception as caught:
                error = error or caught
        if error is not None:
            raise error

    @staticmethod
    def _dispose_page(page):
        try:
            dispose = getattr(page, 'dispose', None)
            if dispose is not None:
                dispose()
        finally:
            if page.winfo_exists():
                page.destroy()

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self._clear()
