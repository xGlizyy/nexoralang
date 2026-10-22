// The NEXORA extension for VS Code.
//
// It starts the language server of the language (a Python process, `python -m
// nexora.lsp`) and lets it answer everything: the diagnostics, the completion,
// the hover, the navigation, the symbols and the formatting.
//
// The server does the work with the same lexer, parser and checker the command
// line uses, so what the editor says about a program is what `nex check` says.

import * as fs from 'node:fs';
import * as path from 'node:path';
import * as vscode from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

/** The Python that runs the server, with the package installed. */
function pythonPath(context: vscode.ExtensionContext): string {
    const configured = vscode.workspace.getConfiguration('nexora').get<string>('python.path');
    if (configured && configured.trim() !== '') {
        return configured.trim();
    }
    // Inside the development of the project, the interpreter of its own
    // environment is the one that has the package installed.
    const local = path.join(context.extensionPath, '..', 'nexora', '.venv', 'Scripts', 'python.exe');
    if (process.platform === 'win32' && fs.existsSync(local)) {
        return local;
    }
    return 'python';
}

function serverOptions(context: vscode.ExtensionContext): ServerOptions {
    return {
        command: pythonPath(context),
        args: ['-m', 'nexora.lsp'],
        transport: TransportKind.stdio,
        options: { cwd: context.extensionPath },
    };
}

function clientOptions(): LanguageClientOptions {
    return {
        documentSelector: [{ language: 'nexora' }],
        outputChannelName: 'NEXORA',
        middleware: {
            // The server offers the formatting; this decides whether the editor uses it.
            provideDocumentFormattingEdits: async (document, options, token, next) => {
                const enabled = vscode.workspace
                    .getConfiguration('nexora')
                    .get<boolean>('format.enable', true);
                if (!enabled) {
                    return [];
                }
                return next(document, options, token);
            },
        },
    };
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    const server = new LanguageClient(
        'nexora',
        'NEXORA language server',
        serverOptions(context),
        clientOptions(),
    );
    client = server;

    const trace = vscode.workspace.getConfiguration('nexora').get<string>('trace.server', 'off');
    if (trace !== 'off') {
        server.setTrace(trace as any);
    }

    await server.start();

    // Format on save, when the setting says so.
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (document) => {
            if (document.languageId !== 'nexora') {
                return;
            }
            const onSave = vscode.workspace
                .getConfiguration('nexora')
                .get<boolean>('format.onSave', false);
            if (!onSave) {
                return;
            }
            await vscode.commands.executeCommand('editor.action.formatDocument');
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nexora.check', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                return;
            }
            const document = editor.document;
            const channel = vscode.window.createOutputChannel('NEXORA');
            channel.show(true);
            const { spawn } = await import('node:child_process');
            const child = spawn(
                pythonPath(context),
                ['-m', 'nexora', 'check', document.uri.fsPath],
                { cwd: path.dirname(document.uri.fsPath) },
            );
            let output = '';
            child.stdout.on('data', (piece: Buffer) => {
                output += piece.toString();
            });
            child.stderr.on('data', (piece: Buffer) => {
                output += piece.toString();
            });
            child.on('close', (code: number) => {
                channel.appendLine(
                    output.trim() === '' ? `nex check: no problems (code ${code})` : output,
                );
            });
        }),
        vscode.commands.registerCommand('nexora.restartServer', async () => {
            await client?.stop();
            const restarted = new LanguageClient(
                'nexora',
                'NEXORA language server',
                serverOptions(context),
                clientOptions(),
            );
            client = restarted;
            await restarted.start();
        }),
    );
}

export async function deactivate(): Promise<void> {
    await client?.stop();
    client = undefined;
}
