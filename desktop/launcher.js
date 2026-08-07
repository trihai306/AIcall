/**
 * Electron Launcher
 *
 * Runs the Electron app from `app/` subdirectory which does NOT contain
 * node_modules/electron, so Electron's internal require('electron')
 * resolves correctly to the API module instead of the npm path helper.
 */
const { spawn } = require('child_process');
const path = require('path');

const electronBinary = require('electron');
const appDir = path.join(__dirname, 'app');

const args = [appDir, ...process.argv.slice(2)];
console.log('[launcher] Binary:', electronBinary);
console.log('[launcher] App dir:', appDir);

const child = spawn(electronBinary, args, {
  stdio: 'inherit',
  cwd: appDir,
});

child.on('exit', (code) => process.exit(code || 0));
process.on('SIGINT', () => { child.kill(); process.exit(); });
process.on('SIGTERM', () => { child.kill(); process.exit(); });
