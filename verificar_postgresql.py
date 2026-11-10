"""Ejecuta comprobaciones PostgreSQL y registra ambas salidas como texto."""
from pathlib import Path
import os
import subprocess
import sys

RAIZ = Path(__file__).resolve().parent


def ejecutar_con_registro(argumentos, registro):
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    # Django escribe su progreso normal en stderr. Se combina aquí, antes
    # de llegar a PowerShell 5.1, que puede convertirlo en NativeCommandError.
    with subprocess.Popen(argumentos, cwd=RAIZ, env=entorno, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding="utf-8", errors="replace") as proceso:
        try:
            while True:
                caracter = proceso.stdout.read(1)
                if not caracter:
                    break
                sys.stdout.write(caracter)
                sys.stdout.flush()
                registro.write(caracter)
                if caracter == "\n":
                    registro.flush()
            return proceso.wait()
        except KeyboardInterrupt:
            if proceso.poll() is None:
                proceso.terminate()
            raise


def main():
    ruta_log = RAIZ / "pruebas-postgresql.log"
    try:
        with ruta_log.open("w", encoding="utf-8") as registro:
            for argumentos in (["check", "--database", "default"], ["test", "maquinaria", "--verbosity", "1"]):
                codigo = ejecutar_con_registro([sys.executable, "-u", str(RAIZ / "manage.py"), *argumentos], registro)
                if codigo:
                    print(f"La comprobacion termino con codigo {codigo}. Revisa {ruta_log}")
                    return codigo
        print(f"Resultado completo guardado en {ruta_log}")
        return 0
    except KeyboardInterrupt:
        print("\nComprobacion interrumpida. El registro conserva la salida recibida.")
        return 130
    except (OSError, ValueError) as error:
        print(f"No se pudo ejecutar la comprobacion: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
