#include<iostream>
using namespace std;
int main()
{
	//check number is positive or negative
	int no;
	cout<<"Enter the value: ";
	cin>>no;
	if(no>0)
	{
		cout<<"Positive Number!";
	}
	else if(no<0)
	{
		cout<<"Negative Number";
	}
	else
	{
		cout<<"Zero is neither positive nor negative.";
	}
}
