param([string] $WavePath = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Web.Extensions
Add-Type -ReferencedAssemblies System.Speech,System.Web.Extensions -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Speech.Recognition;
using System.Threading;
using System.Web.Script.Serialization;
public static class RecorderDictation {
    static readonly object gate = new object();
    static long clock() {
        return (long)((decimal)Stopwatch.GetTimestamp() * 1000000000 / Stopwatch.Frequency);
    }
    static void emit(object value) {
        lock(gate) {
            Console.WriteLine(new JavaScriptSerializer().Serialize(value));
            Console.Out.Flush();
        }
    }
    public static void Run(string wave) {
        using(var engine = new SpeechRecognitionEngine())
        using(var completed = new ManualResetEvent(false)) {
            engine.LoadGrammar(new DictationGrammar());
            if(String.IsNullOrEmpty(wave)) engine.SetInputToDefaultAudioDevice();
            else engine.SetInputToWaveFile(wave);
            long anchor = clock();
            engine.SpeechRecognized += (s,e) => emit(new {
                kind="transcript", text=e.Result.Text, confidence=e.Result.Confidence,
                audio_start_ms=e.Result.Audio.AudioPosition.TotalMilliseconds,
                audio_duration_ms=e.Result.Audio.Duration.TotalMilliseconds,
                stream_anchor_ns=anchor, observed_monotonic_ns=clock()
            });
            engine.SpeechRecognitionRejected += (s,e) => emit(new {
                kind="rejected", text=e.Result == null ? "" : e.Result.Text,
                confidence=e.Result == null ? 0 : e.Result.Confidence,
                observed_monotonic_ns=clock()
            });
            engine.RecognizeCompleted += (s,e) => {
                if(e.Error != null) emit(new { kind="error", text=e.Error.Message });
                completed.Set();
            };
            anchor = clock();
            engine.RecognizeAsync(RecognizeMode.Multiple);
            emit(new { kind="ready", culture=engine.RecognizerInfo.Culture.Name,
                       engine=engine.RecognizerInfo.Id, stream_anchor_ns=anchor });
            if(!String.IsNullOrEmpty(wave)) completed.WaitOne(15000);
            else {
                string line;
                while((line=Console.ReadLine()) != null && line != "stop") {}
            }
            engine.RecognizeAsyncStop();
            if(!completed.WaitOne(2000)) engine.RecognizeAsyncCancel();
        }
    }
}
"@
try { [RecorderDictation]::Run($WavePath) }
catch {
    @{kind='error'; text=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
