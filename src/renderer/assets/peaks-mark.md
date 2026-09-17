# Peaks mark

Generated with the built-in Image Generation tool on 2026-09-04. Used in navigation, the Windows app icon, and the corner credit on match images.

Mode: original generation followed by two image edits. The final asset has a solid black background; screen blending integrates it into the dark interface. It is not a transparent PNG.

Initial direction: an original premium competitive-gaming mark for Peaks, combining an angular P with two ascending mountain peaks; solid white geometry, no wordmark, no imitation of Riot's logo.

Final edit prompt: Keep the exact white geometric P/ascending mountain symbol. Replace the entire checkerboard background with uniform pure black, including all negative space. Uniform white mark with crisp vector-like edges. No transparency, checkerboard, texture, grain, shadow, gradients, border, or text. Center on a black square canvas with a comfortable margin.

Final source: `exec-4de44f6b-cb86-4870-a670-5f112630a686.png` in the session's generated-images folder. The source is retained unchanged.

Windows packaging uses `peaks-mark.ico`, preserved from the successful 2026-09-15 build and checked against this PNG on 2026-09-16. It contains 16, 24, 32, 48, 64, 128, and 256 pixel frames of the same mark. Keeping the ICO in source avoids invoking the PNG conversion tool during every Windows build. Regenerate it alongside the PNG if the mark changes.
