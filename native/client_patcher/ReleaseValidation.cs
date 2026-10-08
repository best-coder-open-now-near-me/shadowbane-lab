using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using ShadowbaneLocal;
public sealed class LocalTransport : ITransport {
    public string root; public int downloads;
    public byte[] Metadata(string url,CancellationToken token) { throw new NotSupportedException(); }
    public void Download(Bundle bundle,string target,Action<string> progress,CancellationToken token) {
        token.ThrowIfCancellationRequested();downloads++;
        File.Copy(Path.Combine(root,bundle.name),target);
    }
}
public static class ReleaseValidation {
    public static int Main(string[] args) {
        try {
            if(args.Length!=2) throw new Exception("Supply release directory and a new empty test client directory.");
            var manifest=Engine.Parse<Manifest>(File.ReadAllBytes(Path.Combine(args[0],"client-manifest.json")));
            string root=Path.GetFullPath(args[1]);if(Directory.Exists(root))throw new Exception("Test target must not already exist.");
            var transport=new LocalTransport {root=Path.GetFullPath(args[0])};
            Engine.Apply(manifest,root,transport,Console.WriteLine,CancellationToken.None,Engine.ClosedGame);
            if(transport.downloads!=manifest.bundles.Length)throw new Exception("Fresh installation did not use every bundle.");
            string preferences=Path.Combine(root,"Config/ArcanePref.cfg");
            File.AppendAllText(preferences,"SOUND= FALSE\r\nUSER_SENTINEL= preserved\r\n");
            string prefsHash=Engine.HashFile(preferences);
            string settings=Path.Combine(root,"Config/ServerSelection.cfg");string settingsHash=Engine.HashFile(settings);
            File.WriteAllText(Path.Combine(root,"player-settings-test.txt"),"Retain this user file.");
            File.WriteAllText(Path.Combine(root,"sb.exe"),"Simulated damaged executable.");
            transport.downloads=0;
            Engine.Apply(manifest,root,transport,Console.WriteLine,CancellationToken.None,Engine.ClosedGame);
            if(transport.downloads!=1||Engine.HashFile(preferences)!=prefsHash||Engine.HashFile(settings)!=settingsHash)
                throw new Exception("Repair did not preserve settings or fetched unrelated bundles.");
            transport.downloads=0;
            Engine.Apply(manifest,root,transport,delegate(string text){},CancellationToken.None,Engine.ClosedGame);
            if(transport.downloads!=0||Engine.HashFile(preferences)!=prefsHash||Engine.HashFile(settings)!=settingsHash||
               !File.Exists(Path.Combine(root,"player-settings-test.txt"))||Directory.Exists(Path.Combine(root,".shadowbane-stage")))
                throw new Exception("No-op validation failed.");
            Console.WriteLine("FULL_RELEASE_VALIDATED: fresh install, one-bundle repair, no-op update, preserved preferences/settings, no retained downloads.");
            return 0;
        } catch(Exception error) {Console.Error.WriteLine(error);return 1;}
    }
}
