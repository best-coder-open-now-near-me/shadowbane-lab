using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading;
using ShadowbaneLocal;

public sealed class TestTransport : ITransport {
    public string archive; public int downloads; public bool fail;
    public byte[] Metadata(string url, CancellationToken token) { throw new NotSupportedException(); }
    public void Download(Bundle bundle, string target, Action<string> progress, CancellationToken token) {
        downloads++; File.Copy(archive,target);
        if (fail) throw new IOException("Simulated interrupted download");
    }
}
public static class PatcherTests {
    static int passed;
    static void Check(bool result,string message) { if (!result) throw new Exception(message); }
    static void Reject(Action action,string name) {
        bool rejected=false; try { action(); } catch (IOException) { rejected=true; }
        Check(rejected,"Expected rejection: "+name); passed++;
    }
    static Manifest Fixture(string archive) {
        var payload = new Dictionary<string,byte[]> {
            {"sb.exe", Encoding.ASCII.GetBytes("reviewed executable")},
            {"cache/CObjects.cache", Encoding.ASCII.GetBytes("reviewed objects")},
            {"ShadowbaneLauncher.exe", Encoding.ASCII.GetBytes("reviewed launcher")},
            {"Config/ArcanePref.cfg", Encoding.ASCII.GetBytes("SOUND= TRUE\r\n")},
            {"Config/ArcaneIP.cfg", Encoding.ASCII.GetBytes("SERVER= original\r\nPORT= 6000\r\n")},
            {"assets/data.bin", Encoding.ASCII.GetBytes("reviewed game data")}
        };
        using (var zip=ZipFile.Open(archive,ZipArchiveMode.Create)) foreach (var pair in payload)
            using (var stream=zip.CreateEntry(pair.Key).Open()) stream.Write(pair.Value,0,pair.Value.Length);
        var bundle=new Bundle { name="client-001.zip", url=Engine.ReleasePrefix+"test/client-001.zip", size=new FileInfo(archive).Length,sha256=Engine.HashFile(archive) };
        return new Manifest {schema_version=1,minimum_patcher=1,version="1.0.0",server="100.87.213.55",port=6000,bundles=new[]{bundle},
            files=payload.Select(p=>new ClientFile {path=p.Key,size=p.Value.Length,sha256=Engine.Hash(p.Value),bundle=bundle.name,policy=Engine.Personal(p.Key)?"seed":"replace"}).ToArray()};
    }
    static void Apply(Manifest manifest,string root,TestTransport transport) {
        Engine.Apply(manifest,root,transport,delegate(string s){},CancellationToken.None,delegate{});
    }
    static Dictionary<string,string> Snapshot(string root) {
        return Directory.GetFiles(root,"*",SearchOption.AllDirectories).ToDictionary(p=>p.Substring(root.Length),Engine.HashFile);
    }
    static bool Same(Dictionary<string,string> a, Dictionary<string,string> b) {
        return a.Count==b.Count && a.All(p=>b.ContainsKey(p.Key)&&b[p.Key]==p.Value);
    }
    public static int Main() {
        string temporary=Path.GetFullPath(Path.Combine(Path.GetTempPath(),"shadowbane-patcher-test-"+Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(temporary);
        try {
            string archive=Path.Combine(temporary,"fixture.zip"),root=Path.Combine(temporary,"client");
            var manifest=Fixture(archive); var transport=new TestTransport {archive=archive};
            Apply(manifest,root,transport);
            Check(transport.downloads==1,"Fresh install did not download the bundle");
            Check(File.ReadAllText(Path.Combine(root,"Config/ArcaneIP.cfg"))=="SERVER= 100.87.213.55\r\nPORT= 6000\r\n","Private endpoint not installed"); passed++;
            string prefs=Path.Combine(root,"Config/ArcanePref.cfg");
            File.WriteAllText(prefs,"SOUND= FALSE\r\nMY_KEY= keep\r\n");
            File.WriteAllText(Path.Combine(root,"saved-user.txt"),"keep this file");
            var before=Snapshot(root); Apply(manifest,root,transport);
            Check(transport.downloads==1 && Same(before,Snapshot(root)),"No-op update downloaded or changed settings"); passed++;
            File.WriteAllText(Path.Combine(root,"sb.exe"),"damaged");
            Apply(manifest,root,transport);
            Check(transport.downloads==2 && File.ReadAllText(prefs).Contains("MY_KEY= keep"),"Repair failed to preserve settings"); passed++;
            Check(!Directory.Exists(Path.Combine(root,".shadowbane-stage")),"Staging directory retained"); passed++;
            byte[] config=Encoding.UTF8.GetBytes("\ufeff# Keep\r\nSERVER= old ; comment\r\nPORT= 1\r\nOTHER= keep\r\n");
            string rewritten=Encoding.UTF8.GetString(Engine.Endpoint(config,"100.87.213.55",6000));
            Check(rewritten=="\ufeff# Keep\r\nSERVER= 100.87.213.55 ; comment\r\nPORT= 6000\r\nOTHER= keep\r\n","Endpoint preservation failed"); passed++;
            Reject(delegate {Engine.Endpoint(Encoding.ASCII.GetBytes("SERVER= one\nSERVER= two\n"),"100.87.213.55",6000);},"duplicate endpoint");
            foreach (var path in new[]{"../outside","/absolute","C:/escape","Config/../escape","cache\\escape","cache/CON.txt","cache/file. ","ShadowbanePatcher.exe"})
                Reject(delegate {Engine.RelativePath(path);},"unsafe path "+path);
            string original=manifest.files[0].path;
            manifest.files[0].path="SB.EXE";
            var copy=manifest.files.ToList();copy.Add(manifest.files[0]);manifest.files=copy.ToArray();
            Reject(delegate {Engine.Validate(manifest);},"case-insensitive duplicate");
            manifest.files=copy.Take(copy.Count-1).ToArray();manifest.files[0].path=original;
            manifest.files[3].policy="replace";
            Reject(delegate {Engine.Validate(manifest);},"settings overwrite");
            manifest.files[3].policy="seed";
            string originalUrl=manifest.bundles[0].url;manifest.bundles[0].url="https://example.com/client.zip";
            Reject(delegate {Engine.Validate(manifest);},"foreign download");manifest.bundles[0].url=originalUrl;
            before=Snapshot(root);
            Reject(delegate {Engine.Apply(manifest,root,transport,delegate(string s){},CancellationToken.None,delegate{throw new IOException("Game running");});},"running game");
            Check(Same(before,Snapshot(root)),"Running-game rejection wrote files"); passed++;
            File.WriteAllText(Path.Combine(root,"sb.exe"),"damaged");
            before=Snapshot(root);string hash=manifest.bundles[0].sha256;manifest.bundles[0].sha256=new string('0',64);
            Reject(delegate {Apply(manifest,root,transport);},"corrupt bundle");
            Check(Same(before,Snapshot(root))&&!Directory.Exists(Path.Combine(root,".shadowbane-stage")),"Corrupt bundle changed files or retained download"); passed++;
            manifest.bundles[0].sha256=hash;transport.fail=true;
            Reject(delegate {Apply(manifest,root,transport);},"interrupted download");
            Check(Same(before,Snapshot(root))&&!Directory.Exists(Path.Combine(root,".shadowbane-stage")),"Failed transfer changed files"); passed++;
            transport.fail=false;
            string fileHash=manifest.files[0].sha256;manifest.files[0].sha256=new string('1',64);
            Reject(delegate {Apply(manifest,root,transport);},"corrupt extracted file");
            Check(Same(before,Snapshot(root)),"Corrupt file replaced installed contents");passed++;
            manifest.files[0].sha256=fileHash;
            using(var zip=ZipFile.Open(archive,ZipArchiveMode.Update)) using(var entry=zip.CreateEntry("../escape").Open()) entry.WriteByte(1);
            manifest.bundles[0].size=new FileInfo(archive).Length;manifest.bundles[0].sha256=Engine.HashFile(archive);
            Reject(delegate {Apply(manifest,root,transport);},"ZIP traversal");
            Check(Same(before,Snapshot(root)),"Malformed archive modified the client");passed++;
            var canceled=new CancellationTokenSource();canceled.Cancel();bool stopped=false;
            try {Engine.Apply(manifest,root,transport,delegate(string s){},canceled.Token,delegate{});}
            catch(OperationCanceledException){stopped=true;}
            Check(stopped&&Same(before,Snapshot(root)),"Cancellation failed");passed++;
            Console.WriteLine(passed+" patcher checks passed.");return 0;
        } catch(Exception error) {Console.Error.WriteLine(error);return 1;}
        finally {
            string basePath=Path.GetFullPath(Path.GetTempPath()).TrimEnd('\\')+"\\";
            if(!temporary.StartsWith(basePath,StringComparison.OrdinalIgnoreCase)||
                !Path.GetFileName(temporary).StartsWith("shadowbane-patcher-test-",StringComparison.Ordinal))
                throw new IOException("Unsafe fixture cleanup path");
            Directory.Delete(temporary,true);
        }
    }
}
