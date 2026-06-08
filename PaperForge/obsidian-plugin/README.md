# PaperForge Obsidian Plugin

An Obsidian plugin that integrates with the PaperForge CLI to import academic papers as structured knowledge bases in your vault.

## Installation

### From Obsidian Community Plugins (coming soon)
1. Open Settings > Community Plugins
2. Search for "PaperForge"
3. Install and enable

### Manual Installation
1. Download the latest release from GitHub
2. Extract to `.obsidian/plugins/paperforge/` in your vault
3. Enable the plugin in Settings > Community Plugins

### Prerequisites
- [PaperForge CLI](https://github.com/yourusername/PaperForge) must be installed
- Python 3.10+ required for the CLI

## Configuration

Open Settings > PaperForge to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| CLI Path | `paperforge` | Path to the paperforge executable |
| Papers Directory | `papers` | Where papers are stored (relative to vault) |
| Default Translate Mode | `off` | Translation: off, abstract, or full |
| Auto-open Index | `true` | Open index.md after importing |

## Commands

Access via Command Palette (`Ctrl/Cmd + P`):

| Command | Description |
|---------|-------------|
| **Import PDF** | Import a PDF paper into your vault |
| **Rebuild Library Index** | Rebuild the master index of all papers |
| **Refresh Citation Links** | Update citation connections between papers |
| **Doctor** | Check PaperForge installation and dependencies |
| **Open Paper Dashboard** | Open sidebar view with paper list |

## Features

### Import PDF
- Select a PDF file from your filesystem
- PaperForge extracts metadata, abstract, and creates structured notes
- Auto-opens the generated `index.md` on completion
- Real-time progress logging in a modal

### Paper Dashboard
- Sidebar view showing all imported papers
- Displays title, year, and status for each paper
- Click any paper to open its index.md
- Refresh button to update the list

### Progress Tracking
- All CLI operations show a progress modal
- Real-time stdout/stderr display
- Success/failure notifications

## File Structure

After importing a paper, the following structure is created:

```
papers/
  <paper-slug>/
    index.md          # Main paper note with metadata
    abstract.md       # Abstract (optionally translated)
    notes.md          # Your reading notes
    figures/          # Extracted figures
    references.md     # Bibliography
```

## Development

```bash
cd obsidian-plugin
npm install
npm run dev    # Watch mode
npm run build  # Production build
```

## Screenshots

*Coming soon*

## License

MIT