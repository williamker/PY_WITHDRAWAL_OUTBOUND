ECHO OFF
REM -------------------------------
REM Variables
REM -------------------------------
SET "PROG_NAME=PY_WITHDRAWAL_OUTBOUND"
SET "SCRIPT_ROOT=%~dp0"
SET "APPLICATION_ROOT=%SCRIPT_ROOT%.."
SET "VENVS_DIR=%APPLICATION_ROOT%\venvs"
SET "VENV_DIR=%VENVS_DIR%\.venv"
SET "PROGRAMS_DIR=%APPLICATION_ROOT%\programs"
SET "LAUNCHER_LOGS_DIR=%APPLICATION_ROOT%\launcher_logs"
SET "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
SET "ACTIVATE_BAT=%VENV_DIR%\Scripts\activate.bat"
SET "REQUIREMENTS_FILE=%APPLICATION_ROOT%\requirements.txt"
SET MY_DATE=%DATE:~6,4%.%DATE:~3,2%.%DATE:~0,2%

IF NOT EXIST "%LAUNCHER_LOGS_DIR%" MD "%LAUNCHER_LOGS_DIR%"
SET "LOG_FILE=%LAUNCHER_LOGS_DIR%\%PROG_NAME%.cmd_%MY_DATE%.log"
SET RETURN_CODE=0

REM -------------------------------
REM Script Start
REM -------------------------------
ECHO ===================================== START OF %PROG_NAME%.cmd =====================================
ECHO ===================================== START OF %PROG_NAME%.cmd ===================================== >> "%LOG_FILE%"

ECHO Host=%COMPUTERNAME%
ECHO Host=%COMPUTERNAME% >> "%LOG_FILE%"

FOR /F "delims=" %%A IN ('py --version 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)

FOR /F "delims=" %%A IN ('where python 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)

FOR /F "delims=" %%A IN ('pip --version 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)

FOR /F "delims=" %%A IN ('where pip 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)

ECHO PROG_NAME=%PROG_NAME%
ECHO PROG_NAME=%PROG_NAME%  >> "%LOG_FILE%"
ECHO SCRIPT_ROOT=%SCRIPT_ROOT%
ECHO SCRIPT_ROOT=%SCRIPT_ROOT%  >> "%LOG_FILE%"
ECHO APPLICATION_ROOT=%APPLICATION_ROOT%
ECHO APPLICATION_ROOT=%APPLICATION_ROOT%  >> "%LOG_FILE%"
ECHO VENV_DIR=%VENV_DIR%
ECHO VENV_DIR=%VENV_DIR%  >> "%LOG_FILE%"
ECHO PROGRAMS_DIR=%PROGRAMS_DIR%
ECHO PROGRAMS_DIR=%PROGRAMS_DIR%  >> "%LOG_FILE%"
ECHO REQUIREMENTS_FILE=%REQUIREMENTS_FILE%
ECHO REQUIREMENTS_FILE=%REQUIREMENTS_FILE%  >> "%LOG_FILE%"

REM -------------------------------
REM Block 1: Create virtual environment
REM -------------------------------
ECHO ==================================================================== >> "%LOG_FILE%"
ECHO Creating virtual environment in %VENV_DIR%
ECHO Creating virtual environment in %VENV_DIR% >> "%LOG_FILE%"

FOR /F "delims=" %%A IN ('py -m venv "%VENV_DIR%" 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)
IF %ERRORLEVEL% NEQ 0 (
    ECHO Creation of virtual environment  KO >> "%LOG_FILE%"
    SET RETURN_CODE=10
    GOTO END_SCRIPT
)
ECHO Creation of virtual environment  OK >> "%LOG_FILE%"

REM -------------------------------
REM Block 2: Activate virtual environment
REM -------------------------------
ECHO ==================================================================== >> "%LOG_FILE%"
ECHO Activating virtual environment...
ECHO Activating virtual environment... >> "%LOG_FILE%"

FOR /F "delims=" %%A IN ('CALL "%ACTIVATE_BAT%" 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)
IF %ERRORLEVEL% NEQ 0 (
    ECHO Virtual environment activation  KO >> "%LOG_FILE%"
    SET RETURN_CODE=20
    GOTO END_SCRIPT
)
ECHO Virtual environment activated  OK >> "%LOG_FILE%"

REM -------------------------------
REM Block 3: Install Python requirements
REM -------------------------------
ECHO ==================================================================== >> "%LOG_FILE%"
ECHO Installing Python requirements from %REQUIREMENTS_FILE%...
ECHO Installing Python requirements from %REQUIREMENTS_FILE%... >> "%LOG_FILE%"

SET "INSTALL_REQUIREMENT_CMD=%PYTHON_EXE% -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r "%REQUIREMENTS_FILE%""

FOR /F "delims=" %%A IN ('%INSTALL_REQUIREMENT_CMD% 2^>^&1') DO (
    ECHO %%A
    ECHO %%A >> "%LOG_FILE%"
)
IF %ERRORLEVEL% NEQ 0 (
    ECHO Python requirements installation  KO >> "%LOG_FILE%"
    SET RETURN_CODE=30
    GOTO END_SCRIPT
)
ECHO Python requirements installed  OK >> "%LOG_FILE%"

REM -------------------------------
REM Block 4: Execute Python program
REM -------------------------------
ECHO ==================================================================== >> "%LOG_FILE%"
ECHO Executing Python program main.py...
ECHO Executing Python program main.py... >> "%LOG_FILE%"

"%PYTHON_EXE%" "%PROGRAMS_DIR%\main.py"  %PROG_NAME%

IF %ERRORLEVEL% NEQ 0 (
    ECHO Execution of Python program  KO >> "%LOG_FILE%"
    SET RETURN_CODE=50
    GOTO END_SCRIPT
)
ECHO Python program executed  OK >> "%LOG_FILE%"

:END_SCRIPT
ECHO returnCode: %RETURN_CODE%
ECHO returnCode: %RETURN_CODE% >> "%LOG_FILE%"
ECHO ===================================== END OF %PROG_NAME%.cmd =====================================
ECHO ===================================== END OF %PROG_NAME%.cmd ===================================== >> "%LOG_FILE%"

EXIT /B %RETURN_CODE%
