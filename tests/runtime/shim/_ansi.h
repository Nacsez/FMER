/* Host-test declaration adapter only. Never included in firmware builds. */
#ifndef FMER_TEST_ANSI_H
#define FMER_TEST_ANSI_H
#include <stdint.h>
#include <wchar.h>
#define _DEFUN(name,args,decls) name(decls)
#define _EXFUN(name,args) name args
#define _AND ,
#define _CONST const
#define _PTR void *
#define _VOID void
#define _DEFUN_VOID(name) name(void)
typedef int32_t __int32_t;
typedef uint32_t __uint32_t;
#endif
