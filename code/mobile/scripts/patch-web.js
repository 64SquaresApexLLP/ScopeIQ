const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// 1. Ensure fbjs/lib/warning.js exists
const fbjsLibDir = path.join(__dirname, '..', 'node_modules', 'fbjs', 'lib');
const fbjsWarning = path.join(fbjsLibDir, 'warning.js');

if (fs.existsSync(fbjsLibDir) && !fs.existsSync(fbjsWarning)) {
  fs.writeFileSync(
    fbjsWarning,
    "var warning = function(condition, format, ...args) { if (!condition && typeof console !== 'undefined') { console.warn(format, ...args); } }; module.exports = warning; module.exports.default = warning;\n"
  );
  console.log('✓ Patched fbjs/lib/warning.js');
}

// 2. Ensure @expo/vector-icons fonts exist
const fontDestDir = path.join(
  __dirname,
  '..',
  'node_modules',
  '@expo',
  'vector-icons',
  'build',
  'vendor',
  'react-native-vector-icons',
  'Fonts'
);

if (fs.existsSync(path.dirname(fontDestDir)) && !fs.existsSync(fontDestDir)) {
  try {
    console.log('Extracting missing vector icon fonts...');
    const mobileDir = path.join(__dirname, '..');
    execSync('npm pack @expo/vector-icons@15.1.1', { cwd: mobileDir, stdio: 'ignore' });
    const tgz = path.join(mobileDir, 'expo-vector-icons-15.1.1.tgz');
    if (fs.existsSync(tgz)) {
      execSync(`tar -xzf "${tgz}"`, { cwd: mobileDir, stdio: 'ignore' });
      const srcFonts = path.join(mobileDir, 'package', 'build', 'vendor', 'react-native-vector-icons', 'Fonts');
      if (fs.existsSync(srcFonts)) {
        fs.cpSync(srcFonts, fontDestDir, { recursive: true });
        console.log('✓ Restored vector icon fonts');
      }
      fs.rmSync(path.join(mobileDir, 'package'), { recursive: true, force: true });
      fs.rmSync(tgz, { force: true });
    }
  } catch (err) {
    console.warn('Warning: Could not auto-extract fonts:', err.message);
  }
}
