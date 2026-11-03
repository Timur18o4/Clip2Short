const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
for (const name of ['dashboard.html','studio.html']) {
  const text = fs.readFileSync(path.join(__dirname,'../clip2short',name),'utf8');
  for (const match of text.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(match[1],{filename:name});
}
console.log('JavaScript der lokalen Oberflächen ohne Syntaxfehler.');
