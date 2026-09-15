# Artwork assets

Finished Canva exports live here. Nothing in this tree is referenced until it
is registered — see `src/art/registry.ts` (illustrations, and the house rules
for how much of it a page gets) and `src/art/backdrop.ts` (page background
layers). `pets/index.ts` groups the pet files into families (`petAssets`) with
their shared canvas sizes (`petAssetSizes`); the registry reads from it.

```
assets/
  pets/
    cats/      cat-orange-peek-{open,wink}, cat-gray-peek-{open,wink},
               cat-gray-side-peek-{1,2}, cat-orange-rest-base + -tail-{1,2,3}
    dogs/      dog-sleep-base + dog-sleep-z{1,2,3}
    misc/      any other animal
  motifs/      small decorations: paw.svg, bone.svg, heart.svg, bowl.svg, toy.svg …
  patterns/    seamless repeating tiles for the page background (WebP or SVG)
  textures/    paper / grain overlays for the page background (WebP)
```

Conventions that keep the animation system working:

- **Files of one family share one canvas.** Every file in a family is exported
  at the same artboard size with the pet in the same place, so they can be
  stacked and swapped by opacity alone. Two shapes of family:
  - *frames* — complete alternate drawings (`cat-…-open` + `cat-…-wink`,
    side-peek pose 1 + pose 2); one shows at a time.
  - *layers* — a body file that always shows plus overlay-only files (Z's, a
    tail) that take turns on top of it.
- **Peeking art carries an edge measurement** (`bodyBottom` / `edge` in
  `pets/index.ts`): where the card edge should cross the image. The registry
  passes it on so paws hang over the edge and drawn wall lines stay hidden.
- **Transparent backgrounds**, so a frame can sit over cream, ivory or peach.
- **Prefer SVG** for illustrations; use WebP for the pattern/texture tiles.
- File names are free-form — the registry maps them to slots.
