// Print the text lines macOS Vision recognizes in an image.
//
//   ocr_text <image>           one recognized line per output line
//   ocr_text <image> --boxes   "#image W H" header, then one
//                              "x<TAB>y<TAB>w<TAB>h<TAB>text" line per text
//                              (image PIXELS, top-left origin)
//
// Used by roll_session.py to read the piano roll's title as FL draws it
// ("Piano roll - <channel>" — the API caption omits the channel name) and by
// import_midi.py to find FL's self-drawn menu rows by their text instead of
// fixed pixel offsets.
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1,
      let img = NSImage(contentsOfFile: args[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("usage: ocr_text <image> [--boxes]\n".data(using: .utf8)!)
    exit(2)
}
let boxes = args.contains("--boxes")
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
try VNImageRequestHandler(cgImage: cg).perform([req])
let W = Double(cg.width), H = Double(cg.height)
if boxes { print("#image \(cg.width) \(cg.height)") }
for obs in req.results ?? [] {
    guard let top = obs.topCandidates(1).first else { continue }
    if boxes {
        let b = obs.boundingBox  // normalized, bottom-left origin
        let x = Int(b.minX * W), y = Int((1 - b.maxY) * H)
        let w = Int(b.width * W), h = Int(b.height * H)
        print("\(x)\t\(y)\t\(w)\t\(h)\t\(top.string)")
    } else {
        print(top.string)
    }
}
