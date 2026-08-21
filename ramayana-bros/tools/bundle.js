#!/usr/bin/env node
/* Inlines css/ and js/ into one self-contained HTML file, so the game can
 * be opened from a file:// URL, e-mailed, or dropped on any static host.
 *
 *   node tools/bundle.js            -> dist/ramayana-bros.html
 */
'use strict';

var fs = require('fs');
var path = require('path');

var root = path.resolve(__dirname, '..');
var read = function (p) { return fs.readFileSync(path.join(root, p), 'utf8'); };

var html = read('index.html');

html = html.replace(/[ \t]*<link rel="stylesheet" href="([^"]+)">\n?/g, function (_, href) {
  return '<style>\n' + read(href).trim() + '\n</style>\n';
});

html = html.replace(/[ \t]*<script src="([^"]+)"><\/script>\n?/g, function (_, src) {
  // </script> inside a source file would close the wrapper early
  return '<script>\n' + read(src).replace(/<\/script/gi, '<\\/script').trim() + '\n</script>\n';
});

if (/<(link|script)[^>]+(href|src)=/.test(html)) {
  console.error('bundle: some external references were not inlined');
  process.exit(1);
}

var outDir = path.join(root, 'dist');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
var out = path.join(outDir, 'ramayana-bros.html');
fs.writeFileSync(out, html);
console.log('wrote ' + path.relative(root, out) + '  (' + (html.length / 1024).toFixed(1) + ' KB)');
