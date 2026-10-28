// Regenera cabecalho.png a partir de cabecalho.html (ver o comentário lá).
//
//   node comunicacoes_financeiras/assets/gerar_cabecalho.js
//
// Precisa de Playwright (Node) com Chromium. É ferramenta de quem mexe no
// visual, não dependência do disparo: o PNG gerado fica versionado.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

(async () => {
  const aqui = __dirname;
  const html = fs.readFileSync(path.join(aqui, 'cabecalho.html'), 'utf8')
    .replace('{logo_branco}', pathToFileURL(path.join(aqui, 'logo_branco.png')).href);
  const temp = path.join(aqui, '_cabecalho_render.html');
  fs.writeFileSync(temp, html);
  try {
    const nav = await chromium.launch();
    const pag = await nav.newPage({ viewport: { width: 600, height: 150 }, deviceScaleFactor: 2 });
    await pag.goto(pathToFileURL(temp).href);
    await pag.waitForTimeout(300);
    await pag.locator('.faixa').screenshot({ path: path.join(aqui, 'cabecalho.png') });
    await nav.close();
  } finally {
    fs.unlinkSync(temp);
  }
  console.log(path.join(aqui, 'cabecalho.png'));
})();
