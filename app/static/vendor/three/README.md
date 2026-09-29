# three.js (vendored)

`three.module.js` and `three.core.js` copied unchanged from the npm package `three` **0.186.1**
(https://threejs.org), MIT license (`LICENSE`). Used by the 3D note highway (`highway3d.js`),
loaded on first use so the app works offline and without npm.

`RoundedBoxGeometry.js` comes from the same package (`examples/jsm/geometries/`); its only change is
the import line, `from 'three'` → `from './three.module.js'`, so it loads without an import map.
