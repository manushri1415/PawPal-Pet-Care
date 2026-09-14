# Artwork assets

Drop finished Canva exports here. Nothing in this tree is referenced until it
is registered — see `src/art/registry.ts` (illustrations) and
`src/art/backdrop.ts` (page background layers).

```
assets/
  pets/
    cats/      cat-open.svg, cat-wink.svg, cat-peek-top.svg, cat-peek-side.svg …
    dogs/      dog-sleep-1z.svg, dog-sleep-2z.svg, dog-sleep-3z.svg …
    misc/      any other animal
  motifs/      small decorations: paw.svg, bone.svg, heart.svg, bowl.svg, toy.svg …
  patterns/    seamless repeating tiles for the page background (WebP or SVG)
  textures/    paper / grain overlays for the page background (WebP)
```

Conventions that keep the animation system working:

- **Frames of one animation share one canvas.** `cat-open.svg` and
  `cat-wink.svg` must be exported at the same artboard size with the cat in
  the same place; the same goes for `dog-sleep-1z/2z/3z`. They are stacked
  and only their opacity changes.
- **Transparent backgrounds**, so a frame can sit over cream, ivory or peach.
- **Prefer SVG** for illustrations; use WebP for the pattern/texture tiles.
- File names are free-form — the registry maps them to slots.
