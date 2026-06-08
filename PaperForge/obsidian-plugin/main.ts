import { App, Plugin, PluginSettingTab, Setting, Modal, Notice, TFile, ItemView, WorkspaceLeaf } from 'obsidian';
import { spawn } from 'child_process';
import * as path from 'path';

interface PaperForgeSettings {
  cliPath: string;
  papersDir: string;
  defaultTranslate: string;
  autoOpenIndex: boolean;
}

const DEFAULT_SETTINGS: PaperForgeSettings = {
  cliPath: 'paperforge',
  papersDir: 'papers',
  defaultTranslate: 'off',
  autoOpenIndex: true,
};

export default class PaperForgePlugin extends Plugin {
  settings: PaperForgeSettings;

  async onload() {
    await this.loadSettings();
    this.addSettingTab(new PaperForgeSettingTab(this.app, this));

    this.addCommand({
      id: 'import-pdf',
      name: 'Import PDF',
      callback: () => this.importPdf()
    });

    this.addCommand({
      id: 'rebuild-index',
      name: 'Rebuild Library Index',
      callback: () => this.runCliCommand('rebuild-index')
    });

    this.addCommand({
      id: 'refresh-links',
      name: 'Refresh Citation Links',
      callback: () => this.runCliCommand('relink')
    });

    this.addCommand({
      id: 'doctor',
      name: 'Doctor',
      callback: () => this.runCliCommand('doctor')
    });

    this.addCommand({
      id: 'open-dashboard',
      name: 'Open Paper Dashboard',
      callback: () => this.activateDashboardView()
    });

    this.registerView('paperforge-dashboard', (leaf) => new PaperForgeDashboard(leaf, this));

    this.addRibbonIcon('book-open', 'PaperForge', () => this.activateDashboardView());
  }

  async onunload() {
    // Clean up
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  getVaultPath(): string {
    const adapter = this.app.vault.adapter;
    if ('basePath' in adapter) {
      return (adapter as any).basePath;
    }
    return '';
  }

  async importPdf() {
    const vaultPath = this.getVaultPath();
    if (!vaultPath) {
      new Notice('PaperForge: Could not detect vault path');
      return;
    }

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf';

    input.onchange = async (e: Event) => {
      const target = e.target as HTMLInputElement;
      const file = target.files?.[0];
      if (!file) return;

      const pdfPath = file.path || file.name;
      const modal = new ProgressModal(this.app, 'PaperForge: Importing PDF...');
      modal.open();

      const args = ['ingest', pdfPath, '--vault', vaultPath, '--translate', this.settings.defaultTranslate];
      const proc = spawn(this.settings.cliPath, args);

      let indexMd = '';

      proc.stdout.on('data', (data: Buffer) => {
        const text = data.toString();
        modal.appendLog(text);

        const match = text.match(/Output:\s*(.*)/);
        if (match) {
          indexMd = match[1].trim() + '/index.md';
        }
      });

      proc.stderr.on('data', (data: Buffer) => {
        modal.appendLog(`[stderr] ${data.toString()}`);
      });

      proc.on('close', (code: number | null) => {
        if (code === 0) {
          modal.appendLog('\nDone! Import successful.');
          new Notice('PaperForge: Import successful');

          if (this.settings.autoOpenIndex && indexMd) {
            const relativePath = path.relative(vaultPath, indexMd);
            this.app.workspace.openLinkText(relativePath, '', true);
          }
        } else {
          modal.appendLog(`\nFailed with exit code ${code}`);
          new Notice(`PaperForge: Import failed (exit ${code})`);
        }
      });

      proc.on('error', (err: Error) => {
        modal.appendLog(`\nError: ${err.message}`);
        new Notice(`PaperForge: Error - ${err.message}`);
      });
    };

    input.click();
  }

  async runCliCommand(command: string) {
    const vaultPath = this.getVaultPath();
    if (!vaultPath) {
      new Notice('PaperForge: Could not detect vault path');
      return;
    }

    const modal = new ProgressModal(this.app, `PaperForge: Running ${command}...`);
    modal.open();

    const args = [command, '--vault', vaultPath];
    const proc = spawn(this.settings.cliPath, args);

    proc.stdout.on('data', (data: Buffer) => {
      modal.appendLog(data.toString());
    });

    proc.stderr.on('data', (data: Buffer) => {
      modal.appendLog(`[stderr] ${data.toString()}`);
    });

    proc.on('close', (code: number | null) => {
      if (code === 0) {
        modal.appendLog('\nDone!');
        new Notice(`PaperForge: ${command} completed`);
      } else {
        modal.appendLog(`\nFailed with exit code ${code}`);
        new Notice(`PaperForge: ${command} failed (exit ${code})`);
      }
    });

    proc.on('error', (err: Error) => {
      modal.appendLog(`\nError: ${err.message}`);
      new Notice(`PaperForge: Error - ${err.message}`);
    });
  }

  async activateDashboardView() {
    const existing = this.app.workspace.getLeavesOfType('paperforge-dashboard');
    if (existing.length) {
      this.app.workspace.revealLeaf(existing[0]);
      return;
    }

    const leaf = this.app.workspace.getRightLeaf(false);
    if (leaf) {
      await leaf.setViewState({
        type: 'paperforge-dashboard',
        active: true,
      });
      this.app.workspace.revealLeaf(leaf);
    }
  }
}

class ProgressModal extends Modal {
  private logEl: HTMLElement;
  private title: string;

  constructor(app: App, title: string) {
    super(app);
    this.title = title;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.addClass('paperforge-modal');

    contentEl.createEl('h3', { text: this.title });

    this.logEl = contentEl.createEl('div', { cls: 'paperforge-log' });
    this.logEl.style.fontFamily = 'monospace';
    this.logEl.style.fontSize = '12px';
    this.logEl.style.maxHeight = '400px';
    this.logEl.style.overflowY = 'auto';
    this.logEl.style.padding = '8px';
    this.logEl.style.backgroundColor = 'var(--background-secondary)';
    this.logEl.style.borderRadius = '4px';
    this.logEl.style.whiteSpace = 'pre-wrap';

    const buttonContainer = contentEl.createEl('div', { cls: 'paperforge-modal-buttons' });
    buttonContainer.style.marginTop = '12px';
    buttonContainer.style.textAlign = 'right';

    const closeBtn = buttonContainer.createEl('button', { text: 'Close' });
    closeBtn.addEventListener('click', () => this.close());
  }

  onClose() {
    const { contentEl } = this;
    contentEl.empty();
  }

  appendLog(text: string) {
    this.logEl.appendText(text);
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }
}

interface PaperEntry {
  slug: string;
  title: string;
  year: string;
  status: string;
}

class PaperForgeDashboard extends ItemView {
  private plugin: PaperForgePlugin;
  private listEl: HTMLElement | null = null;

  constructor(leaf: WorkspaceLeaf, plugin: PaperForgePlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return 'paperforge-dashboard';
  }

  getDisplayText(): string {
    return 'PaperForge Papers';
  }

  getIcon(): string {
    return 'book-open';
  }

  async onOpen() {
    const container = this.containerEl.children[1];
    container.empty();
    container.addClass('paperforge-dashboard');

    const header = container.createEl('div', { cls: 'paperforge-dashboard-header' });
    header.createEl('h4', { text: 'PaperForge Papers' });

    const refreshBtn = header.createEl('button', { text: 'Refresh', cls: 'paperforge-refresh-btn' });
    refreshBtn.addEventListener('click', () => this.loadPapers());

    this.listEl = container.createEl('div', { cls: 'paperforge-paper-list' });

    await this.loadPapers();
  }

  async onClose() {
    // Clean up
  }

  async loadPapers() {
    if (!this.listEl) return;

    this.listEl.empty();
    this.listEl.createEl('div', { text: 'Loading...', cls: 'paperforge-loading' });

    const vaultPath = this.plugin.getVaultPath();
    if (!vaultPath) {
      this.listEl.empty();
      this.listEl.createEl('div', { text: 'Could not detect vault path', cls: 'paperforge-error' });
      return;
    }

    try {
      const papers = await this.getPapersList(vaultPath);
      this.listEl.empty();

      if (papers.length === 0) {
        this.listEl.createEl('div', { text: 'No papers found. Import a PDF to get started.', cls: 'paperforge-empty' });
        return;
      }

      for (const paper of papers) {
        const item = this.listEl.createEl('div', { cls: 'paperforge-paper-item' });

        const titleEl = item.createEl('div', { cls: 'paperforge-paper-title' });
        titleEl.textContent = paper.title;

        const metaEl = item.createEl('div', { cls: 'paperforge-paper-meta' });
        metaEl.textContent = `${paper.year} | ${paper.status}`;

        const slugEl = item.createEl('div', { cls: 'paperforge-paper-slug' });
        slugEl.textContent = paper.slug;

        item.addEventListener('click', () => {
          const indexPath = paper.paper_dir
            ? `${paper.paper_dir}/index.md`
            : `${this.plugin.settings.papersDir}/${paper.year}/${paper.slug}/index.md`;
          this.app.workspace.openLinkText(indexPath, '', true);
        });
      }
    } catch (err) {
      this.listEl.empty();
      this.listEl.createEl('div', {
        text: `Error loading papers: ${err instanceof Error ? err.message : String(err)}`,
        cls: 'paperforge-error'
      });
    }
  }

  async getPapersList(vaultPath: string): Promise<PaperEntry[]> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.plugin.settings.cliPath, ['list', '--vault', vaultPath, '--format', 'json']);
      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on('close', (code: number | null) => {
        if (code !== 0) {
          reject(new Error(stderr || `Exit code ${code}`));
          return;
        }

        try {
          const papers = JSON.parse(stdout);
          resolve(Array.isArray(papers) ? papers : []);
        } catch {
          // Fallback: try to parse line-by-line output
          const papers: PaperEntry[] = [];
          const lines = stdout.split('\n').filter(line => line.trim());

          for (const line of lines) {
            const match = line.match(/(\S+)\s+\[(\d{4})\]\s+(.*?)\s+\[(\w+)\]/);
            if (match) {
              papers.push({
                slug: match[1],
                title: match[3],
                year: match[2],
                status: match[4]
              });
            }
          }

          resolve(papers);
        }
      });

      proc.on('error', (err: Error) => {
        reject(err);
      });
    });
  }
}

class PaperForgeSettingTab extends PluginSettingTab {
  plugin: PaperForgePlugin;

  constructor(app: App, plugin: PaperForgePlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl('h2', { text: 'PaperForge Settings' });

    new Setting(containerEl)
      .setName('CLI Path')
      .setDesc('Path to the paperforge CLI executable')
      .addText(text => text
        .setPlaceholder('paperforge')
        .setValue(this.plugin.settings.cliPath)
        .onChange(async (value) => {
          this.plugin.settings.cliPath = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Papers Directory')
      .setDesc('Directory where papers will be stored (relative to vault root)')
      .addText(text => text
        .setPlaceholder('papers')
        .setValue(this.plugin.settings.papersDir)
        .onChange(async (value) => {
          this.plugin.settings.papersDir = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Default Translate Mode')
      .setDesc('Translation mode for paper abstracts and content')
      .addDropdown(dropdown => dropdown
        .addOption('off', 'Off')
        .addOption('abstract', 'Abstract Only')
        .addOption('full', 'Full Translation')
        .setValue(this.plugin.settings.defaultTranslate)
        .onChange(async (value) => {
          this.plugin.settings.defaultTranslate = value;
          await this.plugin.saveSettings();
        }));

    new Setting(containerEl)
      .setName('Auto-open Index')
      .setDesc('Automatically open index.md after importing a PDF')
      .addToggle(toggle => toggle
        .setValue(this.plugin.settings.autoOpenIndex)
        .onChange(async (value) => {
          this.plugin.settings.autoOpenIndex = value;
          await this.plugin.saveSettings();
        }));
  }
}