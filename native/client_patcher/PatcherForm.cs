using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ShadowbaneLocal {
public sealed class PatcherForm : Form {
    readonly Label status = new Label();
    readonly TextBox folder = new TextBox();
    readonly Button browse = new Button();
    readonly Button update = new Button();
    readonly Button play = new Button();
    readonly ProgressBar progress = new ProgressBar();
    readonly Label version = new Label();
    CancellationTokenSource cancellation;
    Manifest ready;
    bool working, closing;
    public PatcherForm() {
        Text = "Shadowbane Local"; StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(620, 330); FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false; Font = new Font("Segoe UI", 10); BackColor = Color.FromArgb(25,29,35);
        ForeColor = Color.FromArgb(235,237,241);
        var title = new Label { Text = "SHADOWBANE LOCAL", AutoSize = true, Font = new Font("Segoe UI", 23, FontStyle.Bold), Location = new Point(25,20) };
        version.SetBounds(28,69,550,24); version.Text = "Private client  |  Automatic updates";
        var hint = new Label { Text = "Keep Tailscale connected. Choose your dedicated game folder.", Location = new Point(28,104), Size = new Size(565,26) };
        folder.SetBounds(28,138,460,28); folder.ReadOnly = true; folder.BackColor = Color.FromArgb(44,49,58); folder.ForeColor = ForeColor;
        browse.Text = "Browse"; browse.SetBounds(500,137,90,30); browse.Click += delegate { ChooseFolder(); };
        status.SetBounds(28,184,565,46); status.Text = "Choose an existing client or an empty folder for a full installation.";
        progress.SetBounds(28,236,563,12); progress.Style = ProgressBarStyle.Continuous;
        update.Text = "Install / update"; update.SetBounds(28,267,160,38); update.Click += async delegate { await Check(); };
        play.Text = "Play"; play.SetBounds(430,267,160,38); play.Enabled = false; play.Click += delegate { Launch(); };
        foreach (var button in new[] { browse,update,play }) {
            button.FlatStyle = FlatStyle.Flat; button.BackColor = Color.FromArgb(53,63,76); button.ForeColor = ForeColor;
        }
        Controls.AddRange(new Control[] { title,version,hint,folder,browse,status,progress,update,play });
        var beside = Application.StartupPath;
        if (File.Exists(Path.Combine(beside,"sb.exe")) || Directory.Exists(Path.Combine(beside,"cache"))) folder.Text = beside;
        Shown += async delegate {
            if (folder.Text.Length != 0) await Check();
            else ChooseFolder();
        };
        FormClosing += delegate(object sender, FormClosingEventArgs e) {
            if (working) { closing = true; cancellation.Cancel(); status.Text = "Stopping safely..."; e.Cancel = true; }
        };
    }
    void ChooseFolder() {
        using (var picker = new FolderBrowserDialog()) {
            picker.Description = "Choose your dedicated private-server folder, or create an empty folder for the complete client.";
            picker.ShowNewFolderButton = true;
            if (folder.Text.Length != 0) picker.SelectedPath = folder.Text;
            if (picker.ShowDialog(this) == DialogResult.OK) {
                if (Path.GetPathRoot(picker.SelectedPath).TrimEnd('\\') == picker.SelectedPath.TrimEnd('\\')) {
                    MessageBox.Show(this,"Choose a game subfolder, not the root of a drive."); return;
                }
                folder.Text = picker.SelectedPath; ready = null; play.Enabled = false;
                status.Text = "Click Install / update. Existing personal settings will be kept.";
            }
        }
    }
    void Say(string text) {
        if (IsDisposed || !IsHandleCreated) return;
        BeginInvoke((Action)delegate { if (!IsDisposed) status.Text = text; });
    }
    async Task Check() {
        if (working || folder.Text.Length == 0) { if (!working) ChooseFolder(); return; }
        string root = Path.GetFullPath(folder.Text);
        working = true; ready = null; play.Enabled = false; browse.Enabled = false; update.Enabled = false;
        progress.Style = ProgressBarStyle.Marquee; cancellation = new CancellationTokenSource();
        var token = cancellation.Token;
        try {
            ready = await Task.Run(delegate {
                Engine.ClosedGame(); Say("Checking our published client version...");
                var transport = new HttpTransport();
                var release = Engine.CheckChannel(transport, token);
                Engine.Apply(release,root,transport,Say,token,Engine.ClosedGame);
                token.ThrowIfCancellationRequested();
                string self = Process.GetCurrentProcess().MainModule.FileName;
                string installed = Path.Combine(root,"ShadowbanePatcher.exe");
                Engine.PlainPath(installed);
                if (!String.Equals(Path.GetFullPath(self),Path.GetFullPath(installed),StringComparison.OrdinalIgnoreCase) &&
                    (!File.Exists(installed) || Engine.HashFile(self) != Engine.HashFile(installed))) {
                    Engine.Atomic(installed,File.ReadAllBytes(self));
                }
                Engine.Atomic(Path.Combine(root,"Play-ShadowbaneLocal.cmd"),Encoding.ASCII.GetBytes(
                    "@echo off\r\nstart \"\" \"%~dp0ShadowbanePatcher.exe\"\r\n"));
                Engine.Atomic(Path.Combine(root,"ShadowbaneLocal.release.json"),Encoding.UTF8.GetBytes(
                    "{\"version\":\"" + release.version + "\",\"checked_utc\":\"" + DateTime.UtcNow.ToString("o") + "\"}\n"));
                return release;
            },token);
            version.Text = "Client " + ready.version + "  |  Up to date";
            status.Text = "Ready. Use Play-ShadowbaneLocal.cmd in this folder for future updates and play.";
            play.Enabled = true; update.Text = "Check / repair";
        } catch (OperationCanceledException) {
            ready = null; status.Text = "Update stopped. Run the patcher again to finish.";
        } catch (Exception error) {
            ready = null; status.Text = "Update did not finish: " + error.Message;
            MessageBox.Show(this,error.Message + "\n\nNo game was launched. Click Install / update to retry.",
                "Shadowbane update",MessageBoxButtons.OK,MessageBoxIcon.Warning);
        } finally {
            working = false; cancellation.Dispose(); cancellation = null;
            progress.Style = ProgressBarStyle.Continuous; browse.Enabled = true; update.Enabled = true;
            if (closing) Close();
        }
    }
    void Launch() {
        if (ready == null || working) return;
        try {
            Engine.ClosedGame();
            string root = Path.GetFullPath(folder.Text);
            var launcher = Array.Find(ready.files, f => f.path.Equals("ShadowbaneLauncher.exe",StringComparison.OrdinalIgnoreCase));
            string path = Engine.Destination(root,launcher.path);
            if (!Engine.Matches(path,launcher)) throw new IOException("Launcher changed. Run Check / repair.");
            Process.Start(new ProcessStartInfo(path) { WorkingDirectory = root, UseShellExecute = false });
            Close();
        } catch (Exception error) { MessageBox.Show(this,error.Message,"Cannot start Shadowbane"); }
    }
}
public static class Program {
    [STAThread] public static void Main() {
        System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12;
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new PatcherForm());
    }
}
}
